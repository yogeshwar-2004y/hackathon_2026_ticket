# Support Ticket Router

Lightweight Flask-based support ticket routing system.

Project goal
- Implement Milestone 1 (keyword router) and Milestone 2 (transformer-based background enhancement).
- Milestone 3 prepared as boilerplate placeholders only.

How to install

1. Create a Python 3.10+ virtualenv and activate it:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Running

- Milestone 1 (synchronous keyword router):
  ```bash
  export ROUTER_MODE=m1
  python run.py
  ```

- Milestone 2 (async model-enhanced router):
  ```bash
  export ROUTER_MODE=m2
  python run.py
  ```

Milestone 2 as separate services (API + Celery worker)
------------------------------------------------------

Run these in separate terminals.

1) Start infra (Redis/Mongo):

```bash
docker compose up -d
```

2) Start API service:

Linux/macOS:
```bash
export ROUTER_MODE=m2
export REDIS_URL=redis://127.0.0.1:6379/0
python run.py
```

Windows PowerShell:
```powershell
$env:ROUTER_MODE="m2"
$env:REDIS_URL="redis://127.0.0.1:6379/0"
python run.py
```

3) Start Celery worker service:

Linux/macOS:
```bash
export ROUTER_MODE=m2
export REDIS_URL=redis://127.0.0.1:6379/0
python run_m2_worker.py
```

Windows PowerShell:
```powershell
$env:ROUTER_MODE="m2"
$env:REDIS_URL="redis://127.0.0.1:6379/0"
python run_m2_worker.py
```

Milestone 3 worker from root
----------------------------

Windows PowerShell:
```powershell
$env:REDIS_URL="redis://127.0.0.1:6379/0"
python run_m3_worker.py
```

Linux/macOS:
```bash
export REDIS_URL=redis://127.0.0.1:6379/0
python run_m3_worker.py
```

Example curl

```bash
curl -X POST http://127.0.0.1:5000/tickets \
  -H "Content-Type: application/json" \
  -d '{"subject":"Billing issue","body":"I was charged twice, please refund ASAP!!","customer":"alice@example.com"}'
```

Status

- Milestone 1 & 2 fully working. Milestone 3 prepared as boilerplate only.


Frontend (optional)
-------------------

This repo includes a minimal React + Vite frontend in `frontend/` that can be used
to submit tickets from a browser.

How to run frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend talks to the backend at `http://127.0.0.1:5000/tickets`. Run the Flask
app first, then the frontend dev server.

Redis & Mongo (optional - for M2 broker & persistence)
----------------------------------------------------
This project can use Redis as a broker (incoming task list + priority sorted set)
and MongoDB to persist tickets. If you enable these services the backend will
enqueue tickets to Redis and store ticket documents in MongoDB.

Install & run locally (macOS examples):

```bash
# Redis
brew install redis
redis-server /usr/local/etc/redis.conf

# MongoDB (Community)
brew tap mongodb/brew
brew install mongodb-community@6.0
brew services start mongodb-community@6.0
```

Environment variables:

- REDIS_URL (default: redis://127.0.0.1:6379/0)
- MONGO_URI (default: mongodb://127.0.0.1:27017)

When Redis/Mongo are running, start the backend (M2 mode) as before:

```bash
export ROUTER_MODE=m2
export REDIS_URL=redis://127.0.0.1:6379/0
export MONGO_URI=mongodb://127.0.0.1:27017
python run.py
```

The background worker will BRPOP from Redis incoming list and push processed
tickets into a Redis sorted set for priority.

