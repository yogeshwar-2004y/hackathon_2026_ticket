"""Milestone 2 package.

Keep package import side-effect free so Celery can load
`app.milestone2.celery_worker` without importing optional heavy modules.
"""

__all__ = ["celery_worker", "intelligent_queue", "intelligent_queue_flask"]
