# INS Challenge Backend (FastAPI)

Підготовлений стартовий backend під командний план:

- модульний sensor fusion шар (`EKF`, `UKF`, `complementary`),
- фонові обрахунки через Celery + Redis,
- міграції БД через Alembic,
- API для upload/trajectory/metrics/status,
- Docker-стек для локального старту однією командою.

## 1. Швидкий старт

```bash
cd backend
docker compose up --build
```

Сервіси:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- PostgreSQL host-port: `5433` (щоб не конфліктувати з локальним `5432`)

На старті API автоматично виконує `alembic upgrade head`.

## 2. Ключові ендпоінти

Обов'язкові з плану:

- `POST /api/v1/upload` — завантажити raw лог (+ optional ground truth), створити run, опційно відправити в чергу.
- `GET /api/v1/trajectory?run_id=...` — отримати обчислену траєкторію.
- `GET /api/v1/metrics?run_id=...` — Endpoint Error та RMS Crosstrack.
- `GET /api/v1/status?run_id=...` — статус run + CPU/RAM.

Додаткові:

- `GET /api/v1/benchmark?run_id=...` — `cpu_time_sec`, `wall_time_sec`, `points_per_sec`.
- `POST /api/v1/runs/{run_id}/process?background=true` — ручний запуск обробки.
- `GET /api/v1/runs/{run_id}/trajectory.csv` — скачати CSV результат.

## 3. Приклад upload

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "name=run-from-upload" \
  -F "log_file=@../1_TR-C-Maneuver.BIN" \
  -F "start_stage=PAD_IDLE" \
  -F "end_stage=LANDED" \
  -F "fallback_end_stage=DESCENT" \
  -F "enqueue=true"
```

## 4. Архітектура модулів

- `app/services/sensor_parsing.py` — парсинг BIN/CSV, валідація базових полів.
- `app/services/sensor_preprocessing.py` — outlier cleanup, low/high-pass фільтрація, timestamp alignment, adaptive IMU weighting.
- `app/services/baro_fusion.py` — fusion двох барометрів і корекція висоти.
- `app/services/fusion/` — алгоритми `complementary`, `ekf`, `ukf`.
- `app/services/ins_pipeline.py` — orchestration pipeline + експорт `trajectory.csv`.
- `app/services/run_executor.py` — виконання run з benchmark метриками.
- `app/worker/` — Celery app і задачі.

## 5. Вибір алгоритму fusion

Через env-змінну:

- `FUSION_ALGORITHM=ekf`
- `FUSION_ALGORITHM=ukf`
- `FUSION_ALGORITHM=complementary`

## 6. Міграції Alembic

Локально:

```bash
alembic upgrade head
```

Згенерувати нову ревізію:

```bash
alembic revision -m "describe change"
```

## 7. Що вже готово для старту команди

- Інфраструктура для BE#1 (fusion/preprocess/parser) вже винесена в окремі модулі.
- Інфраструктура для BE#2 (API/upload/metrics/status + Docker + queue + migrations) готова.
- Тестер може одразу писати unit/integration тести проти стабільних endpoint-контрактів.
