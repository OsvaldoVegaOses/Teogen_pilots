from __future__ import annotations

import asyncio
from uuid import UUID

from .celery_app import celery_app


@celery_app.task(name="theory.run_pipeline", bind=True, max_retries=2, default_retry_delay=10)
def run_theory_pipeline_task(self, task_id: str, project_id: str, user_uuid: str, request_payload: dict):
    """
    Celery entrypoint for theory pipeline.
    Executes the async pipeline in worker process event loop.
    """
    from ..api.theory import _run_theory_pipeline
    from ..schemas.theory import TheoryGenerateRequest

    request = TheoryGenerateRequest(**request_payload)
    asyncio.run(
        _run_theory_pipeline(
            task_id=task_id,
            project_id=UUID(project_id),
            user_uuid=UUID(user_uuid),
            request=request,
        )
    )
    return {"task_id": task_id, "status": "queued"}
