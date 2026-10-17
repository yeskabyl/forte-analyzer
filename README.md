# Video Violation Analyzer

Асинхронный сервис для анализа видео на операционные нарушения.
FastAPI принимает файл, Celery-воркер (брокер Redis) анализирует его через OpenCV,
статус и результат хранятся в SQLite (SQLAlchemy).

## Запуск

```bash
docker-compose up --build        # или: docker compose up --build
```

Веб-интерфейс: `http://localhost:3000`. API: `http://localhost:8000`, Swagger UI: `http://localhost:8000/docs` (кнопка **Authorize** → `X-API-Key`).
Если порт 8000 занят: `API_PORT=8010 docker-compose up --build`. Остальные переменные — в `.env.example`.

## API

Все эндпоинты требуют заголовок `X-API-Key` (по умолчанию `forte-secret-key-2026`), иначе `401`.

```bash
# Отправить видео (.mp4 / .mov) -> 202 {"job_id": "..."}
curl -H "X-API-Key: forte-secret-key-2026" -F "file=@video.mp4" http://localhost:8000/v1/analyze

# Статус -> {"job_id", "status": "processing|done|failed", "result", "error"}
curl -H "X-API-Key: forte-secret-key-2026" http://localhost:8000/v1/jobs/<job_id>
```

| Код | Когда |
|-----|-------|
| 202 | Задача принята |
| 400 | Пустой файл |
| 401 | Нет / неверный `X-API-Key` |
| 404 | `job_id` не найден |
| 413 | Файл больше `MAX_UPLOAD_MB` (500 МБ по умолчанию) |
| 415 | Расширение не `.mp4` / `.mov` |
| 503 | Redis недоступен, задача помечена `failed` |

Те же эндпоинты доступны с префиксом `/api/v1` — его использует веб-интерфейс.
CORS включён (`CORS_ORIGINS`, по умолчанию `*`).

## Веб-интерфейс

`frontend/` — React 19 + TypeScript + Vite, Bootstrap 5. В Docker собирается и раздаётся nginx:
**http://localhost:3000** (порт — `WEB_PORT`). nginx проксирует `/api` в контейнер `api`, поэтому браузер
обращается к API со своего же адреса.

Локальная разработка (бэкенд должен работать на `:8000`, либо задайте `VITE_PROXY_TARGET`):

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, /api проксируется на бэкенд
npm test         # vitest
npm run build    # проверка типов + сборка в dist/
```

- Другой адрес API без прокси: `?api=http://localhost:8010` в URL или `VITE_API_BASE_URL` при сборке.
- Ключ в поле по умолчанию — `forte2026` (как в ТЗ фронтенда). Бэкенд по умолчанию ждёт `forte-secret-key-2026`:
  введите его в поле или запустите бэкенд с `API_KEY=forte2026`.
- Понимает оба формата ответа: `{verdict, violations[{type, timecode_sec, description, evidence_frames}]}`
  и `{result: {violation, events[]}}` этого бэкенда. Кадры из `evidence_frames` (base64 без `data:`-префикса)
  показываются галереей с увеличением по клику; этот бэкенд кадры пока не отдаёт.
- Клик по таймкоду перематывает локальное превью видео (если браузер умеет декодировать кодек файла).

## Как устроен анализ

`app/analyzer.py` — **базовая эвристика, не обученная модель**:

1. `duration_sec = CAP_PROP_FRAME_COUNT / CAP_PROP_FPS` (если контейнер не сообщает число кадров — считаются декодированные).
2. Кадры берутся с частотой `ANALYZER_SAMPLE_FPS` (2/с), уменьшаются до 160 px, переводятся в серый, размываются.
3. Для соседних выборок считается доля изменившихся пикселей (frame differencing).
4. Событие `leave_unlocked_workstation` фиксируется, когда всплеск движения (≥ `ANALYZER_MIN_ACTIVE_SEC`)
   сменяется неподвижностью ≥ `ANALYZER_MIN_STILL_SEC`: человек встал и вышел из кадра стационарной камеры.
   Окно события: `[t − 2 с, t + 3 с]`.

Ограничения: эвристика не видит, заблокирован ли ПК, и сработает на любое «движение → тишина»
(например, человек замер). Для продакшена нужен детектор людей/экрана; интерфейс `analyze_video()` → `AnalysisResult`
при этом не меняется. Пороги настраиваются переменными `ANALYZER_*` (см. `app/config.py`).

## Структура

```
forte-video-analyzer/
├── app/
│   ├── main.py         # FastAPI: /v1/analyze, /v1/jobs/{job_id}
│   ├── security.py     # проверка X-API-Key
│   ├── celery_app.py   # Celery + Redis
│   ├── tasks.py        # задача: анализ -> запись в БД -> удаление файла
│   ├── analyzer.py     # OpenCV-анализ
│   ├── schemas.py      # Pydantic-схемы ответа и результата
│   ├── models.py       # таблица jobs
│   ├── database.py     # SQLAlchemy engine (SQLite, WAL)
│   └── config.py       # переменные окружения
├── frontend/           # React SPA (Vite + TS), Dockerfile + nginx.conf
│   └── src/
│       ├── api.ts              # fetch-клиент, поллинг, нормализация ответа
│       ├── useVideoAnalysis.ts # состояние: idle / processing / result
│       └── components/         # форма, статусы, карточки, галерея кадров
├── tests/              # pytest, Celery в eager-режиме, синтетические видео
├── Dockerfile
├── docker-compose.yml  # redis + api + worker, общий том /data
├── requirements.txt
└── requirements-dev.txt
```

## Тесты локально

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest
```

## Заметки по эксплуатации

- SQLite и загруженные файлы лежат в общем томе `app-data`, который монтируют и API, и воркер. Для нескольких
  хостов замените `DATABASE_URL` на PostgreSQL, а файлы — на объектное хранилище.
- `task_acks_late=True`: если воркер упадёт посреди анализа, Redis передаст задачу повторно.
