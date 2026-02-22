import os
import subprocess
import sys


def main() -> int:
    """
    Start Milestone 2 Celery worker as a separate service process.

    Usage:
      python run_m2_worker.py
    """
    env = os.environ.copy()
    env.setdefault("ROUTER_MODE", "m2")
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.milestone2.celery_config:celery_app",
        "worker",
        "--loglevel=info",
        "--pool=solo",
    ]
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
