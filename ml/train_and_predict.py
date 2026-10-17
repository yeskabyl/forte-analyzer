"""Обучение YOLOv8 и поиск нарушения «наличные без присмотра» на видео. Всё локально.

Как запустить
-------------
    pip install -r requirements.txt

1) Обучение. Нужен датасет в формате YOLO и его data.yaml. Проще всего: разметить кадры
   из dataset/frames/ в Roboflow (классы `cash` и `staff`), экспортировать как "YOLOv8"
   и распаковать, например, в dataset/yolo/. В архиве уже будет свой data.yaml —
   передайте путь к нему. Пример формата — ml/data.yaml.

       python train_and_predict.py train --data dataset/yolo/data.yaml --epochs 50

   Базовая модель yolov8n.pt скачивается ultralytics автоматически при первом запуске
   (это просто файл весов, сама модель работает офлайн). Если есть NVIDIA GPU с CUDA —
   ultralytics возьмёт её сам, иначе обучение идёт на CPU (`--device cpu` — принудительно).
   Результаты: runs/detect/<name>/ (графики, метрики), лучшие веса копируются в ./best.pt.

2) Инференс на видео (1 кадр в секунду):

       python train_and_predict.py predict --video videos/X-1.mov --model best.pt
       python train_and_predict.py predict --video videos/X-1.mov --save-frames evidence/

   Печатает JSON: длительность, найдено ли нарушение, список секунд с нарушением и
   объединённые интервалы. С --save-frames сохраняет кадры нарушений с рамками детекций.

Из кода:

    from train_and_predict import detect_violation
    report = detect_violation("videos/X-1.mov", model_path="best.pt")

Правило (эвристика) — пример, а не готовый ответ кейса: в кадре есть `cash` и нет
`staff` → нарушение `unattended_cash` на этой секунде. Его качество целиком зависит от
того, насколько модель обучена находить оба класса; см. unattended_cash_rule().
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import cv2

CASH_CLASS = "cash"
STAFF_CLASS = "staff"
VIOLATION_TYPE = "unattended_cash"


# ---------------------------------------------------------------- обучение


def train(
    data_yaml: str,
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 16,
    device: str | None = None,
    base_model: str = "yolov8n.pt",
    name: str = "cash_staff",
) -> Path:
    """Дообучает yolov8n.pt на датасете из data_yaml. Возвращает путь к ./best.pt."""
    from ultralytics import YOLO  # импорт здесь, чтобы --help работал быстро

    data_path = Path(data_yaml)
    if not data_path.is_file():
        raise FileNotFoundError(f"Не найден {data_path}. Экспортируйте датасет из Roboflow в формате YOLOv8.")

    model = YOLO(base_model)
    model.train(
        data=str(data_path.resolve()),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=str(Path("runs/detect").resolve()),
        name=name,
        exist_ok=True,
        patience=20,  # ранняя остановка, если val-метрики не растут 20 эпох
        seed=0,
    )

    best = Path(model.trainer.best)
    if not best.is_file():
        raise RuntimeError(f"Обучение завершилось, но весов {best} нет")
    target = Path("best.pt").resolve()
    shutil.copy2(best, target)
    print(f"Лучшие веса: {best}\nСкопированы в: {target}")
    return target


# ---------------------------------------------------------------- инференс


def unattended_cash_rule(detections: dict[str, float]) -> bool:
    """Эвристика на один кадр: наличные видны, сотрудника в кадре нет.

    detections — {имя_класса: максимальная уверенность в кадре}, только детекции
    выше порога conf.
    """
    return CASH_CLASS in detections and STAFF_CLASS not in detections


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _merge_seconds(seconds: list[int], step: int = 1) -> list[dict[str, object]]:
    """[5, 6, 7, 12] → интервалы [5..7], [12..12]."""
    intervals: list[dict[str, object]] = []
    for sec in seconds:
        if intervals and sec - intervals[-1]["end_sec"] <= step:
            intervals[-1]["end_sec"] = sec
        else:
            intervals.append({"type_key": VIOLATION_TYPE, "start_sec": sec, "end_sec": sec})
    for interval in intervals:
        interval["timestamp"] = format_timestamp(interval["start_sec"])
    return intervals


def detect_violation(
    video_path: str,
    model_path: str = "best.pt",
    conf: float = 0.4,
    imgsz: int | None = None,
    save_frames_dir: str | None = None,
) -> dict[str, object]:
    """Прогоняет видео через обученную модель по 1 кадру в секунду и применяет правило.

    Возвращает:
        {
          "video": "...", "duration_sec": 25.9, "violation": true,
          "events":    [{"second": 22, "timestamp": "00:22", "type_key": "unattended_cash",
                         "cash_conf": 0.81, "detections": {"cash": 0.81}}],
          "intervals": [{"type_key": "unattended_cash", "start_sec": 22, "end_sec": 24, "timestamp": "00:22"}]
        }
    """
    from ultralytics import YOLO

    if not Path(video_path).is_file():
        raise FileNotFoundError(video_path)
    if not Path(model_path).is_file():
        raise FileNotFoundError(f"Нет весов {model_path}. Сначала: python train_and_predict.py train ...")

    model = YOLO(model_path)
    class_names = {int(k): str(v).lower() for k, v in model.names.items()}
    absent = {CASH_CLASS, STAFF_CLASS} - set(class_names.values())
    if absent:
        raise ValueError(
            f"В модели нет классов {sorted(absent)} (есть: {sorted(class_names.values())}). "
            "Правило unattended_cash требует оба класса — проверьте names в data.yaml."
        )

    # Без imgsz ultralytics берёт размер, на котором модель обучалась (он сохранён в весах).
    # Инференс на другом размере меняет масштаб объектов и может «терять» классы.
    predict_kwargs: dict[str, object] = {"conf": conf, "verbose": False}
    if imgsz:
        predict_kwargs["imgsz"] = imgsz

    save_dir = Path(save_frames_dir) if save_frames_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV не смог открыть {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or math.isnan(fps) or fps <= 0:
            raise RuntimeError("Некорректный FPS видео")
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        events: list[dict[str, object]] = []
        frame_index = 0
        next_second = 0
        decoded = 0
        # Последовательное чтение без перемотки: grab() дешёвый, retrieve() + YOLO —
        # только на кадре, ближайшем к началу каждой секунды.
        while cap.grab():
            decoded += 1
            if frame_index >= round(next_second * fps):
                ok, frame = cap.retrieve()
                if ok:
                    result = model.predict(frame, **predict_kwargs)[0]
                    detections: dict[str, float] = {}
                    for cls_id, score in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist()):
                        label = class_names[int(cls_id)]
                        detections[label] = max(detections.get(label, 0.0), round(float(score), 3))

                    if unattended_cash_rule(detections):
                        events.append({
                            "second": next_second,
                            "timestamp": format_timestamp(next_second),
                            "type_key": VIOLATION_TYPE,
                            "cash_conf": detections[CASH_CLASS],
                            "detections": detections,
                        })
                        if save_dir:
                            stem = Path(video_path).stem
                            cv2.imwrite(str(save_dir / f"{stem}_{next_second:04d}s.jpg"), result.plot())
                next_second += 1
            frame_index += 1
    finally:
        cap.release()

    duration = (frame_count if frame_count > 0 else decoded) / fps
    return {
        "video": str(video_path),
        "duration_sec": round(duration, 1),
        "violation": bool(events),
        "events": events,
        "intervals": _merge_seconds([e["second"] for e in events]),
    }


# ---------------------------------------------------------------- CLI


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLOv8: обучение и поиск нарушения unattended_cash")
    sub = parser.add_subparsers(dest="command", required=True)

    p_train = sub.add_parser("train", help="дообучить yolov8n.pt на data.yaml")
    p_train.add_argument("--data", default="data.yaml", help="data.yaml датасета (экспорт Roboflow → YOLOv8)")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--imgsz", type=int, default=640)
    p_train.add_argument("--batch", type=int, default=16, help="уменьшите до 8/4, если не хватает памяти")
    p_train.add_argument("--device", default=None, help="cpu, 0 (первая GPU) и т.п.; по умолчанию — авто")
    p_train.add_argument("--base-model", default="yolov8n.pt")
    p_train.add_argument("--name", default="cash_staff", help="имя запуска в runs/detect/")

    p_pred = sub.add_parser("predict", help="найти нарушения в видео (1 кадр/с)")
    p_pred.add_argument("--video", required=True)
    p_pred.add_argument("--model", default="best.pt")
    p_pred.add_argument("--conf", type=float, default=0.4, help="порог уверенности детекций")
    p_pred.add_argument("--imgsz", type=int, default=None, help="по умолчанию — размер, на котором обучалась модель")
    p_pred.add_argument("--save-frames", default=None, help="папка для кадров нарушений с рамками")

    args = parser.parse_args()
    if args.command == "train":
        train(args.data, args.epochs, args.imgsz, args.batch, args.device, args.base_model, args.name)
    else:
        report = detect_violation(args.video, args.model, args.conf, args.imgsz, args.save_frames)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


# Защита __main__ обязательна на Windows: загрузчики данных ultralytics запускают
# дочерние процессы, которые заново импортируют этот файл.
if __name__ == "__main__":
    sys.exit(main())
