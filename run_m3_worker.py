import os
import subprocess
import sys


def main() -> int:
    """
    Start Milestone 3 Celery worker as a separate service process.

    Usage:
      python run_m3_worker.py
    """
    env = os.environ.copy()
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.milestone3.Main:app",
        "worker",
        "-Q",
        "high,medium,low",
        "--loglevel=info",
        "--pool=solo",
    ]
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
