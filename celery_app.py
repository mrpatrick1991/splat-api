from celery import Celery
import tasks

import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

REDIS_BROKER_URL = "redis://127.0.0.1:6379/0"
POSTGRES_BACKEND_URL = "db+postgresql://postgres:securepassword@127.0.0.1:5432/mydatabase"

celery = Celery(
    "celery_app",
    broker=REDIS_BROKER_URL,
    backend=POSTGRES_BACKEND_URL
)

celery.conf.update(
    result_backend=POSTGRES_BACKEND_URL,
    result_expires=3600 * 24,  # Expire results after 24 hours
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
celery.autodiscover_tasks(["tasks.splat"], force=True)
print(f"Result backend: {celery.conf['result_backend']}")
