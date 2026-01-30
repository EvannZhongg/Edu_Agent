from __future__ import annotations

import os

from celery import Celery


def create_celery() -> Celery:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_app = Celery(
        "edu_gateway",
        broker=redis_url,
        backend=redis_url,
    )
    return celery_app
