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

