from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
import uuid
import logging

logger = logging.getLogger(__name__)

from ..database import get_db
from ..schemas.interview import InterviewResponse, InterviewCreate
from ..models.models import Interview, Project
from ..services.storage_service import storage_service
from ..services.transcription_service import transcription_service
from sqlalchemy import select

router = APIRouter(prefix="/interviews", tags=["Interviews"])

@router.post("/upload", response_model=InterviewResponse)
async def upload_interview(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    participant_pseudonym: Optional[str] = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    1. Uploads audio/file to Azure Blob Storage
    2. Creates a record in the database
    3. Triggers background transcription
    """
    # Verify project
    project_result = await db.execute(select(Project).filter(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Upload to Azure
    file_ext = file.filename.split(".")[-1] if file.filename else "wav"
    blob_name = f"{project_id}/{uuid.uuid4()}.{file_ext}"
    file_content = await file.read()

    try:
        blob_url = await storage_service.upload_blob("audio", blob_name, file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    # Save to Database
    new_interview = Interview(
        project_id=project_id,
        participant_pseudonym=participant_pseudonym,
        audio_blob_url=blob_url,
        transcription_status="processing",
    )

    db.add(new_interview)
    await db.commit()
    await db.refresh(new_interview)

    # Trigger Background Transcription
    # Pass blob_name (not the full URL) for correct SAS URL generation
    background_tasks.add_task(
        process_transcription,
        new_interview.id,
        blob_name,  # ← FIXED: pass the blob path, not the full URL
    )

    return new_interview

async def process_transcription(interview_id: UUID, blob_name: str):
    """Background task for transcription using axial-speech with gpt-4o fallback."""
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db_session:
        try:
            logger.info(f"Starting transcription for interview {interview_id}")

            # Generate a SAS URL using the correct blob path (project_id/uuid.ext)
            sas_url = await storage_service.generate_sas_url("audio", blob_name)
            logger.info(f"SAS URL generated for blob: {blob_name}")

            result = await transcription_service.transcribe_interview(sas_url)
            logger.info(f"Transcription result received: {result['method']}")

            # Update Database
            interview_result = await db_session.execute(
                select(Interview).filter(Interview.id == interview_id)
            )
            interview = interview_result.scalar_one_or_none()

            if interview:
                interview.full_text = result["full_text"]
                interview.transcription_status = "completed"
                interview.transcription_method = result["method"]  # ← Now exists in ORM
                interview.word_count = len(result["full_text"].split())
                interview.speakers = result.get("segments", [])  # ← Now exists in ORM

                # Create Fragments from segments
                from ..models.models import Fragment
                for segment in result.get("segments", []):
                    new_fragment = Fragment(
                        interview_id=interview_id,
                        text=segment.get("text", ""),
                        speaker_id=str(segment.get("speaker", "Unknown")),
                    )
                    db_session.add(new_fragment)

                await db_session.commit()
                logger.info(f"Transcription and fragmentation completed for interview {interview_id}")

        except Exception as e:
            logger.error(f"Background transcription failed for {interview_id}: {e}")
            # Mark as failed in DB
            try:
                interview_result = await db_session.execute(
                    select(Interview).filter(Interview.id == interview_id)
                )
                interview = interview_result.scalar_one_or_none()
                if interview:
                    interview.transcription_status = "failed"
                    await db_session.commit()
            except Exception as db_err:
                logger.error(f"Failed to mark interview as failed: {db_err}")

@router.get("/{project_id}", response_model=List[InterviewResponse])
async def list_interviews(project_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Interview).filter(Interview.project_id == project_id))
    return result.scalars().all()
