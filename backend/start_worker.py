import os
import sys


def main() -> int:
    """
    Start Celery worker for TheoGen background pipelines.
    Usage:
      python start_worker.py
    """
    cmd = (
        "celery -A app.tasks.celery_app.celery_app worker "
        "--loglevel=INFO --concurrency=4 --hostname=theory-worker@%h"
    )
    return os.system(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
