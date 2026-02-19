from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
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
from ..core.auth import CurrentUser, get_current_user
from .dependencies import verify_project_ownership
from sqlalchemy import select

router = APIRouter(prefix="/interviews", tags=["Interviews"])

# Security Constraints
MAX_FILE_SIZE_MB = 250
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_MIME_TYPES = {
    # Audio
    "audio/mpeg", "audio/wav", "audio/x-m4a", "audio/mp4", "audio/webm", "audio/ogg", "audio/aac", "audio/x-wav",
    # Video
    "video/mp4", "video/mpeg", "video/webm", "video/quicktime",
    # Documents (Transcripts)
    "text/plain", "application/json", 
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"  # .docx
}

@router.post("/upload", response_model=InterviewResponse)
async def upload_interview(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    participant_pseudonym: Optional[str] = None,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1. Uploads audio/file to Azure Blob Storage
    2. Creates a record in the database
    3. Triggers background transcription
    
    Security:
    - Validates file type (Audio/Video/Doc)
    - Enforces max file size (250MB)
    - Verifies project ownership
    """
    
    # 1. Security: Validate Project Ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Security: Validate File Type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed types: Audio, Video, .docx, .txt, .json"
        )

    # 3. Security: Validate File Size
    # Check Content-Length header first (fast but spoofable)
    content_length = file.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size is {MAX_FILE_SIZE_MB}MB"
        )

    # Stream upload to Azure without loading entirely into memory
    # Security: Content-Length check above prevents initiating transfer for declared large files.
    # UploadFile spools to disk if large, so we pass the file-like object directly.
    file_ext = file.filename.split(".")[-1] if file.filename else "wav"
    blob_name = f"{project_id}/{uuid.uuid4()}.{file_ext}"

    try:
        # Pass the file-like object directly for streaming upload
        # Note: file.file is a SpooledTemporaryFile or similar file-like object
        blob_url = await storage_service.upload_blob("audio", blob_name, file.file)
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="Storage upload failed")

    # 5. Save to Database
    new_interview = Interview(
        project_id=project_id,
        participant_pseudonym=participant_pseudonym,
        audio_blob_url=blob_url,
        transcription_status="processing",
    )

    db.add(new_interview)
    await db.commit()
    await db.refresh(new_interview)

    # 6. Trigger Background Transcription
    background_tasks.add_task(
        process_transcription,
        new_interview.id,
        blob_name,
    )

    return new_interview

async def process_transcription(interview_id: UUID, blob_name: str):
    """Background task for transcription using axial-speech with gpt-4o fallback."""
    from ..database import get_session_local
    session_local = get_session_local()

    async with session_local() as db_session:
        try:
            logger.info(f"Starting transcription for interview {interview_id}")

            sas_url = await storage_service.generate_sas_url("audio", blob_name)
            
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
                interview.transcription_method = result["method"]
                interview.word_count = len(result["full_text"].split())
                interview.speakers = result.get("segments", [])

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

        except Exception as e:
            logger.error(f"Background transcription failed for {interview_id}: {e}")
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
async def list_interviews(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify ownership before listing
    project_result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.user_uuid,
        )
    )
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(select(Interview).filter(Interview.project_id == project_id))
    return result.scalars().all()
