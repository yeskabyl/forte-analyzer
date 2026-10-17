"""Подготовка кадров для ручной разметки в Roboflow.

Что делает скрипт
-----------------
1. Читает лист `events` из `annotations_template.xlsx` (pandas + openpyxl).
2. Берёт строки, где `official_label` == "нарушение".
3. Нормализует имя видео из столбца `video`: в таблице перемешаны латинская `X` и
   кириллическая `Х` (а файлы могут называться и так, и так), поэтому и имена в таблице,
   и имена файлов приводятся к одному виду: кириллические двойники → латиница, верхний
   регистр, любые тире → "-", без пробелов. "Х-4", "x-4", "X - 4" → "X-4".
4. Таймкод: если заполнен `event_sec` — берётся он (так требует README шаблона: «пусто =
   берётся официальный таймкод»), иначе `official_time_sec`.
5. Открывает видео через cv2.VideoCapture и сохраняет 3 кадра: t-1 с, t, t+1 с
   (смещение настраивается флагом --offset). Видео читается с начала через grab() без
   перемотки: для .mov (H.264/HEVC) перемотка CAP_PROP_POS_FRAMES в OpenCV может
   «промахнуться» на несколько кадров, а так номер кадра (и секунда) известны точно.
6. Пишет .jpg в `dataset/frames/` и `manifest.csv` с привязкой файла к видео и секунде.

Как запустить
-------------
    pip install -r requirements.txt

    # видео лежат в папке videos/ (можно во вложенных папках), таблица — рядом:
    python prepare_data.py --xlsx annotations_template.xlsx --videos-dir videos

    # все параметры:
    python prepare_data.py --help

Имена файлов кадров: `<видео>_<таймкод>s_<m1|0|p1>.jpg`, например `X-1_22.0s_m1.jpg` —
кадр видео X-1 за 1 секунду до нарушения на 22.0 с. Дальше папку `dataset/frames/`
загружают в Roboflow, размечают классы (например `cash`, `staff`) и экспортируют
датасет в формате "YOLOv8" — его data.yaml используется в train_and_predict.py.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import pandas as pd

VIDEO_EXTENSIONS = {".mov", ".mp4"}
VIOLATION_LABEL = "нарушение"

# Кириллические буквы, которые выглядят как латинские. В названиях видео встречается
# в основном "Х", но остальные дешевле учесть сразу, чем ловить потом.
CYRILLIC_TO_LATIN = str.maketrans({
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x",
})
DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"})


def normalize_video_name(name: str) -> str:
    """'Х-4' (кириллица), 'x-4', 'X - 4', 'Х-4.MOV' → 'X-4'."""
    text = unicodedata.normalize("NFKC", str(name)).strip()
    stem = Path(text).stem if Path(text).suffix.lower() in VIDEO_EXTENSIONS else text
    stem = stem.translate(CYRILLIC_TO_LATIN).translate(DASHES)
    return "".join(stem.split()).upper()


@dataclass(frozen=True)
class ViolationRow:
    video: str  # нормализованное имя
    raw_video: str  # как записано в таблице
    event_sec: float


def read_violations(xlsx_path: Path) -> list[ViolationRow]:
    df = pd.read_excel(xlsx_path, sheet_name="events")
    required = {"video", "official_label", "official_time_sec"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"На листе 'events' нет столбцов: {sorted(missing)}")

    labels = df["official_label"].astype(str).str.strip().str.lower()
    violations = df[labels == VIOLATION_LABEL]

    rows: list[ViolationRow] = []
    seen: set[tuple[str, float]] = set()
    for _, row in violations.iterrows():
        event = row.get("event_sec")
        time_sec = event if pd.notna(event) else row["official_time_sec"]
        if pd.isna(time_sec):
            print(f"[!] {row['video']}: нет таймкода (ни event_sec, ни official_time_sec) — пропуск")
            continue
        item = ViolationRow(normalize_video_name(row["video"]), str(row["video"]), float(time_sec))
        if (item.video, item.event_sec) in seen:
            continue
        seen.add((item.video, item.event_sec))
        rows.append(item)
    return rows


def index_videos(videos_dir: Path) -> dict[str, Path]:
    """Нормализованное имя → путь. Ищет рекурсивно, регистр расширения не важен (.MOV/.mov)."""
    index: dict[str, Path] = {}
    for path in sorted(videos_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        key = normalize_video_name(path.stem)
        if key in index:
            print(f"[!] Два файла с именем {key}: {index[key].name} и {path.name} — используется первый")
            continue
        index[key] = path
    return index


def extract_frames(video_path: Path, times_sec: list[float]) -> list[tuple[float, "cv2.typing.MatLike"]]:
    """Возвращает [(фактическая_секунда, кадр)] для запрошенных секунд (в порядке возрастания).

    Время за пределами видео прижимается к первому/последнему кадру.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV не смог открыть {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not fps or math.isnan(fps) or fps <= 0:
            raise RuntimeError(f"{video_path.name}: некорректный FPS")
        last_index = frame_count - 1 if frame_count > 0 else None

        def to_index(t: float) -> int:
            idx = max(0, round(t * fps))
            return min(idx, last_index) if last_index is not None else idx

        targets = sorted({to_index(t) for t in times_sec})
        # Без перемотки: grab() идёт с первого кадра, поэтому номер кадра точно известен.
        current = 0

        frames: list[tuple[float, "cv2.typing.MatLike"]] = []
        wanted = iter(targets)
        target = next(wanted)
        while True:
            if not cap.grab():
                break
            if current >= target:
                ok, frame = cap.retrieve()
                if ok:
                    frames.append((current / fps, frame))
                target = next(wanted, None)
                if target is None:
                    break
            current += 1
        return frames
    finally:
        cap.release()


def offset_tag(offset: float) -> str:
    if offset == 0:
        return "0"
    return f"{'p' if offset > 0 else 'm'}{abs(offset):g}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Вырезает кадры вокруг нарушений для разметки в Roboflow")
    parser.add_argument("--xlsx", type=Path, default=Path("annotations_template.xlsx"), help="Excel с листом events")
    parser.add_argument("--videos-dir", type=Path, default=Path("videos"), help="папка с .mov (ищется рекурсивно)")
    parser.add_argument("--out", type=Path, default=Path("dataset/frames"), help="куда сохранить .jpg")
    parser.add_argument("--offset", type=float, default=1.0, help="смещение кадров до/после таймкода, сек")
    parser.add_argument("--jpeg-quality", type=int, default=95)
    args = parser.parse_args()

    if not args.xlsx.is_file():
        print(f"Файл {args.xlsx} не найден")
        return 1
    if not args.videos_dir.is_dir():
        print(f"Папка {args.videos_dir} не найдена")
        return 1

    violations = read_violations(args.xlsx)
    videos = index_videos(args.videos_dir)
    print(f"Нарушений в таблице: {len(violations)}; видео в папке: {len(videos)}")

    args.out.mkdir(parents=True, exist_ok=True)
    offsets = [-args.offset, 0.0, args.offset]
    manifest_rows: list[dict[str, object]] = []
    missing: list[str] = []
    failed: list[str] = []

    for item in violations:
        video_path = videos.get(item.video)
        if video_path is None:
            missing.append(item.raw_video)
            continue
        try:
            requested = [item.event_sec + o for o in offsets]
            frames = extract_frames(video_path, requested)
        except RuntimeError as exc:
            failed.append(f"{item.raw_video}: {exc}")
            continue

        # Если видео короче t+1 или t-1 < 0, несколько смещений попадут в один кадр —
        # такой кадр сохраняется один раз, под первым подходящим смещением.
        saved_for_event = 0
        used_frames: set[float] = set()
        for offset, want in zip(offsets, requested):
            if not frames:
                break
            frame_sec, frame = min(frames, key=lambda f: abs(f[0] - want))
            if frame_sec in used_frames:
                continue
            used_frames.add(frame_sec)
            name = f"{item.video}_{item.event_sec:.1f}s_{offset_tag(offset)}.jpg"
            if not cv2.imwrite(str(args.out / name), frame, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality]):
                failed.append(f"{item.raw_video}: не удалось записать {name}")
                continue
            saved_for_event += 1
            manifest_rows.append({
                "file": name,
                "video": item.raw_video,
                "video_file": video_path.name,
                "event_sec": item.event_sec,
                "offset_sec": offset,
                "frame_sec": round(frame_sec, 3),
            })
        print(f"[ok] {item.raw_video} ({video_path.name}) t={item.event_sec:g}s → {saved_for_event} кадр(а)")

    if manifest_rows:
        with (args.out / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys()))
            writer.writeheader()
            writer.writerows(manifest_rows)

    print(f"\nСохранено кадров: {len(manifest_rows)} → {args.out.resolve()}")
    if missing:
        print(f"Не найдены видео ({len(missing)}): {', '.join(missing)}")
    if failed:
        print("Ошибки:\n  " + "\n  ".join(failed))
    return 0 if manifest_rows else 1


if __name__ == "__main__":
    sys.exit(main())
