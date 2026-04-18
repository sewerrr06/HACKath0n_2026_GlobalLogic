# Team Kickoff Guide

Документ фіксує стартову рамку робіт під ваш розподіл ролей.

## 1. Backend Dev #1 (Core INS)

Робочі файли:

- `app/services/sensor_parsing.py`
- `app/services/sensor_preprocessing.py`
- `app/services/fusion/complementary.py`
- `app/services/fusion/ekf.py`
- `app/services/fusion/ukf.py`
- `app/services/ins_pipeline.py`

Перші задачі:

1. Уточнити формати вхідних сенсорних даних та доробити parser/validator для всіх потрібних полів.
2. Поліпшити pre-processing (калібрування bias, кращий timestamp alignment, robust outlier detection).
3. Замінити starter EKF/UKF на повну реалізацію фільтра стану.
4. Додати ZUPT event detector і маркери в результаті.

## 2. Backend Dev #2 (API + Infra)

Робочі файли:

- `app/api/routes/challenge.py`
- `app/api/routes/runs.py`
- `app/services/run_executor.py`
- `app/worker/`
- `docker-compose.yml`
- `alembic/`

Перші задачі:

1. Додати WebSocket стрімінг прогресу обчислення.
2. Додати endpoint для confidence per point (після готовності з Core INS).
3. Додати збереження метрик в окремий JSON-артефакт.
4. Додати авторизацію/ліміти upload, якщо потрібно для демо-середовища.

## 3. QA / Tester

Стартовий scope:

1. Unit тести для `metrics.py`, `sensor_preprocessing.py`, `baro_fusion.py`.
2. Integration тести API (`/upload`, `/status`, `/metrics`, `/trajectory`).
3. Стрес-кейси: пошкоджені CSV/BIN, пропущені поля, шумні сенсори.
4. Валідація RMS/Endpoint через незалежний скрипт.

## 4. Git Workflow

1. Базова гілка для інтеграції: `backend`.
2. Feature гілки: `be1/*`, `be2/*`, `qa/*`.
3. Кожен PR має містити: що змінено, як тестувалось, ризики.

## 5. Definition of Done

1. Алгоритм генерує `trajectory.csv` у форматі `timestamp,x,y,z`.
2. Метрики `Endpoint Error` і `RMS Crosstrack Error` віддаються API.
3. Фоновий запуск не блокує API-потік.
4. Міграції повторювано застосовуються на чистій БД.
5. Docker-стек піднімається однією командою.
