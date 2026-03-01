from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any, Set
from uuid import UUID
import uuid
import logging
import asyncio
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
import json as _json

logger = logging.getLogger(__name__)

from ..database import get_db, get_session_local
from ..schemas.interview import (
    InterviewResponse,
    InterviewListItemResponse,
    InterviewTranscriptResponse,
    TranscriptInterviewResponse,
    TranscriptPaginationResponse,
    TranscriptSegmentResponse,
    InterviewExportRequest,
    InterviewExportTaskCreated,
    InterviewExportTaskStatusResponse,
)
from ..models.models import Interview, Project, Fragment, Code, code_fragment_links
from ..services.storage_service import storage_service
from ..services.transcription_service import transcription_service
from ..services.interview_export_service import interview_export_service
from ..core.settings import settings
from ..core.auth import CurrentUser, get_current_user
from .dependencies import verify_project_access, project_scope_condition
from sqlalchemy import select, func
from sqlalchemy.orm import load_only

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

_EXPORT_TASK_TTL = 86400
_EXPORT_TASK_PREFIX = "interview_export_task:"
_redis_client = None
_interview_export_tasks: Dict[str, Dict[str, Any]] = {}
_export_background_tasks: Set[asyncio.Task] = set()


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not (settings.AZURE_REDIS_HOST and settings.AZURE_REDIS_KEY):
        return None
    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.Redis(
            host=settings.AZURE_REDIS_HOST,
            port=settings.REDIS_SSL_PORT,
            password=settings.AZURE_REDIS_KEY,
            ssl=True,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis_client.ping()
    except Exception as e:
        logger.warning("Redis unavailable for interview export tasks: %s", e)
        _redis_client = None
    return _redis_client


def _new_export_task(task_id: str, project_id: UUID, owner_id: UUID) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    return {
        "task_id": task_id,
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "result": None,
        "error": None,
        "project_id": str(project_id),
        "owner_id": str(owner_id),
        "created_at": now,
        "updated_at": now,
    }


async def _persist_export_task(task_id: str) -> None:
    task = _interview_export_tasks.get(task_id)
    if not task:
        return
    redis = await _get_redis()
    if not redis:
        return
    try:
        await redis.setex(
            f"{_EXPORT_TASK_PREFIX}{task_id}",
            _EXPORT_TASK_TTL,
            _json.dumps(task, default=str),
        )
    except Exception as e:
        logger.warning("Failed to persist interview export task %s: %s", task_id, e)


async def _restore_export_task(task_id: str) -> Optional[Dict[str, Any]]:
    if task_id in _interview_export_tasks:
        return _interview_export_tasks[task_id]
    redis = await _get_redis()
    if not redis:
        return None
    try:
        raw = await redis.get(f"{_EXPORT_TASK_PREFIX}{task_id}")
        if raw:
            task = _json.loads(raw)
            _interview_export_tasks[task_id] = task
            return task
    except Exception as e:
        logger.warning("Failed to restore interview export task %s: %s", task_id, e)
    return None


async def _set_export_task_state(
    task_id: str,
    *,
    status_value: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    result: Any = None,
    error: Optional[str] = None,
) -> None:
    task = _interview_export_tasks.get(task_id)
    if not task:
        return
    if status_value is not None:
        task["status"] = status_value
    if progress is not None:
        task["progress"] = max(0, min(100, int(progress)))
    if message is not None:
        task["message"] = message
    if result is not None:
        task["result"] = result
    if error is not None:
        task["error"] = error
    task["updated_at"] = datetime.utcnow().isoformat()
    await _persist_export_task(task_id)


async def _verify_project_ownership(project_id: UUID, user: CurrentUser, db: AsyncSession) -> Project:
    return await verify_project_access(project_id=project_id, user=user, db=db)


def _ms_range(start_ms: Optional[int], end_ms: Optional[int]) -> str:
    if start_ms is None or end_ms is None:
        return ""
    return f"{start_ms}-{end_ms}ms"


def _segments_from_full_text(full_text: str, max_chars: int = 450) -> List[Dict[str, Any]]:
    text = str(full_text or "").strip()
    if not text:
        return []

    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    segments: List[Dict[str, Any]] = []
    for paragraph in paragraphs:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
        if not sentences:
            sentences = [paragraph]
        buffer = ""
        for sentence in sentences:
            candidate = sentence if not buffer else f"{buffer} {sentence}"
            if len(candidate) <= max_chars:
                buffer = candidate
                continue
            if buffer:
                segments.append(
                    {
                        "text": buffer.strip(),
                        "speaker": "Unknown",
                        "offsetMilliseconds": None,
                        "durationMilliseconds": None,
                    }
                )
            if len(sentence) <= max_chars:
                buffer = sentence
            else:
                for idx in range(0, len(sentence), max_chars):
                    chunk = sentence[idx : idx + max_chars].strip()
                    if chunk:
                        segments.append(
                            {
                                "text": chunk,
                                "speaker": "Unknown",
                                "offsetMilliseconds": None,
                                "durationMilliseconds": None,
                            }
                        )
                buffer = ""
        if buffer:
            segments.append(
                {
                    "text": buffer.strip(),
                    "speaker": "Unknown",
                    "offsetMilliseconds": None,
                    "durationMilliseconds": None,
                }
            )

    if segments:
        return segments
    return [
        {
            "text": text,
            "speaker": "Unknown",
            "offsetMilliseconds": None,
            "durationMilliseconds": None,
        }
    ]


async def _build_export_payload(
    db: AsyncSession,
    project: Project,
    interviews: List[Interview],
    include_codes: bool,
    include_metadata: bool,
    include_timestamps: bool,
) -> List[Dict[str, Any]]:
    interview_ids = [i.id for i in interviews]
    if not interview_ids:
        return []

    fragments_result = await db.execute(
        select(Fragment)
        .where(Fragment.interview_id.in_(interview_ids))
        .order_by(Fragment.interview_id.asc(), Fragment.paragraph_index.asc().nullslast(), Fragment.created_at.asc())
    )
    fragments = fragments_result.scalars().all()

    codes_by_fragment: Dict[UUID, List[str]] = {}
    if include_codes and fragments:
        fragment_ids = [f.id for f in fragments]
        cf_rows = await db.execute(
            select(code_fragment_links.c.fragment_id, Code.label)
            .join(Code, Code.id == code_fragment_links.c.code_id)
            .where(code_fragment_links.c.fragment_id.in_(fragment_ids), Code.project_id == project.id)
        )
        for fragment_id, label in cf_rows.all():
            if fragment_id not in codes_by_fragment:
                codes_by_fragment[fragment_id] = []
            if label:
                codes_by_fragment[fragment_id].append(label)

    fragments_by_interview: Dict[UUID, List[Dict[str, Any]]] = {}
    for frag in fragments:
        seg = {
            "fragment_id": str(frag.id),
            "paragraph_index": frag.paragraph_index,
            "speaker_id": frag.speaker_id,
            "start_offset": frag.start_offset,
            "end_offset": frag.end_offset,
            "start_ms": frag.start_ms if include_timestamps else None,
            "end_ms": frag.end_ms if include_timestamps else None,
            "time_range": _ms_range(frag.start_ms, frag.end_ms) if include_timestamps else "",
            "text": frag.text,
            "codes": codes_by_fragment.get(frag.id, []),
        }
        fragments_by_interview.setdefault(frag.interview_id, []).append(seg)

    out: List[Dict[str, Any]] = []
    for interview in interviews:
        item = {
            "id": str(interview.id),
            "segments": fragments_by_interview.get(interview.id, []),
        }
        if include_metadata:
            item.update(
                {
                    "project_id": str(interview.project_id),
                    "participant_pseudonym": interview.participant_pseudonym,
                    "transcription_method": interview.transcription_method,
                    "language": interview.language,
                    "word_count": interview.word_count,
                    "created_at": interview.created_at.isoformat() if interview.created_at else None,
                }
            )
        out.append(item)
    return out


async def _run_interview_export_task(
    task_id: str,
    project_owner_id: UUID,
    project_id: UUID,
    request: InterviewExportRequest,
) -> None:
    await _set_export_task_state(task_id, status_value="running", progress=5, message="Loading interviews")
    session_local = get_session_local()

    try:
        async with session_local() as db:
            project_result = await db.execute(
                select(Project).where(Project.id == project_id, Project.owner_id == project_owner_id)
            )
            project = project_result.scalar_one_or_none()
            if not project:
                await _set_export_task_state(
                    task_id,
                    status_value="failed",
                    progress=100,
                    message="Project not found",
                    error="Project not found",
                )
                return

            query = select(Interview).where(Interview.project_id == project.id)
            if request.scope == "selected":
                if not request.interview_ids:
                    await _set_export_task_state(
                        task_id,
                        status_value="failed",
                        progress=100,
                        message="No interview_ids provided for selected scope",
                        error="No interview_ids provided",
                    )
                    return
                query = query.where(Interview.id.in_(request.interview_ids))
            query = query.order_by(Interview.created_at.asc())

            interviews_result = await db.execute(query)
            interviews = interviews_result.scalars().all()
            if not interviews:
                await _set_export_task_state(
                    task_id,
                    status_value="failed",
                    progress=100,
                    message="No interviews found",
                    error="No interviews found",
                )
                return

            await _set_export_task_state(task_id, progress=35, message="Building export payload")
            payload = await _build_export_payload(
                db=db,
                project=project,
                interviews=interviews,
                include_codes=request.include_codes,
                include_metadata=request.include_metadata,
                include_timestamps=request.include_timestamps,
            )

            await _set_export_task_state(task_id, progress=65, message="Generating file")
            file_bytes, extension, content_type = interview_export_service.generate(
                fmt=request.format,
                project_name=project.name,
                interviews=payload,
            )

            await _set_export_task_state(task_id, progress=85, message="Uploading file")
            blob_name = (
                f"{project_id}/interviews/"
                f"Interviews_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{extension}"
            )
            await storage_service.upload_blob(
                container_key="exports",
                blob_name=blob_name,
                data=file_bytes,
                content_type=content_type,
            )
            download_url = await storage_service.generate_sas_url(
                container_key="exports",
                blob_name=blob_name,
                expires_hours=1,
            )

            await _set_export_task_state(
                task_id,
                status_value="completed",
                progress=100,
                message="Export completed",
                result={
                    "blob_path": blob_name,
                    "download_url": download_url,
                    "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                    "content_type": content_type,
                    "size_bytes": len(file_bytes),
                    "format": extension,
                },
            )
    except Exception as e:
        logger.exception("Interview export task %s failed: %s", task_id, e)
        await _set_export_task_state(
            task_id,
            status_value="failed",
            progress=100,
            message="Export failed",
            error=str(e),
        )

@router.post("/upload", response_model=InterviewResponse)
async def upload_interview(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    participant_pseudonym: Optional[str] = Form(None),
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
    await verify_project_access(project_id=project_id, user=user, db=db)

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
    file_ext = file.filename.split(".")[-1].lower() if file.filename else "wav"
    blob_name = f"{project_id}/{uuid.uuid4()}.{file_ext}"

    # Map extension → MIME type so Azure Speech API can identify the format via SAS URL.
    _AUDIO_MIME = {
        "wav":  "audio/wav",
        "mp3":  "audio/mpeg",
        "mp4":  "audio/mp4",
        "m4a":  "audio/mp4",
        "webm": "audio/webm",
        "ogg":  "audio/ogg",
        "aac":  "audio/aac",
        "flac": "audio/flac",
    }
    audio_content_type = _AUDIO_MIME.get(file_ext, "audio/wav")

    try:
        # Pass the file-like object directly for streaming upload
        # Note: file.file is a SpooledTemporaryFile or similar file-like object
        blob_url = await storage_service.upload_blob("audio", blob_name, file.file, content_type=audio_content_type)
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="Storage upload failed")

    # 5. Save to Database
    normalized_pseudonym = participant_pseudonym.strip() if participant_pseudonym else None

    new_interview = Interview(
        project_id=project_id,
        participant_pseudonym=normalized_pseudonym,
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
    session_local = get_session_local()

    async with session_local() as db_session:
        try:
            logger.info(f"Starting transcription for interview {interview_id}")

            interview_result = await db_session.execute(
                select(Interview).filter(Interview.id == interview_id)
            )
            interview = interview_result.scalar_one_or_none()
            if interview:
                interview.transcription_status = "processing"
                await db_session.commit()

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
                raw_segments = result.get("segments")
                segments = raw_segments if isinstance(raw_segments, list) else []
                if not segments:
                    segments = _segments_from_full_text(result.get("full_text") or "")
                interview.speakers = segments

                # Create Fragments from segments with positional anchors for deep-linking.
                running_offset = 0
                for idx, segment in enumerate(segments, start=1):
                    seg_text = segment.get("text", "") or ""
                    if not seg_text.strip():
                        continue
                    if seg_text:
                        found_pos = interview.full_text.find(seg_text, running_offset)
                        if found_pos < 0:
                            found_pos = interview.full_text.find(seg_text)
                        if found_pos >= 0:
                            start_offset = found_pos
                            end_offset = found_pos + len(seg_text)
                            running_offset = end_offset
                        else:
                            start_offset = None
                            end_offset = None
                    else:
                        start_offset = None
                        end_offset = None

                    offset_ms = segment.get("offsetMilliseconds")
                    duration_ms = segment.get("durationMilliseconds")
                    start_ms = int(offset_ms) if isinstance(offset_ms, (int, float)) else None
                    end_ms = (
                        int(offset_ms + duration_ms)
                        if isinstance(offset_ms, (int, float)) and isinstance(duration_ms, (int, float))
                        else None
                    )

                    new_fragment = Fragment(
                        interview_id=interview_id,
                        text=seg_text,
                        start_offset=start_offset,
                        end_offset=end_offset,
                        paragraph_index=idx,
                        start_ms=start_ms,
                        end_ms=end_ms,
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

async def _list_interviews_impl(
    project_id: UUID,
    user: CurrentUser,
    db: AsyncSession,
):
    # Verify ownership before listing
    await verify_project_access(project_id=project_id, user=user, db=db)

    result = await db.execute(
        select(Interview)
        .options(
            load_only(
                Interview.id,
                Interview.project_id,
                Interview.participant_pseudonym,
                Interview.transcription_status,
                Interview.transcription_method,
                Interview.word_count,
                Interview.language,
                Interview.created_at,
                Interview.audio_blob_url,
            )
        )
        .filter(Interview.project_id == project_id)
        .order_by(Interview.created_at.desc())
    )
    interviews = result.scalars().all()

    now = datetime.utcnow()
    for interview in interviews:
        should_retry_failed = interview.transcription_status == "failed"
        should_retry_stale_processing = (
            interview.transcription_status == "processing"
            and interview.created_at
            and (now - interview.created_at) > timedelta(minutes=10)
        )

        if (should_retry_failed or should_retry_stale_processing) and interview.audio_blob_url:
            parsed = urlparse(interview.audio_blob_url)
            path = parsed.path.lstrip("/")
            container_prefix = "theogen-audio/"
            if path.startswith(container_prefix):
                blob_name = path[len(container_prefix):]
                if blob_name:
                    interview.transcription_status = "retrying"
                    await db.commit()
                    asyncio.create_task(process_transcription(interview.id, blob_name))

    return interviews


@router.get("/project/{project_id}", response_model=List[InterviewListItemResponse])
async def list_interviews(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _list_interviews_impl(project_id=project_id, user=user, db=db)


@router.get("/id/{interview_id}/transcript", response_model=InterviewTranscriptResponse)
async def get_interview_transcript(
    interview_id: UUID,
    include_full_text: bool = Query(False),
    q: Optional[str] = Query(None),
    speaker_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    interview_result = await db.execute(
        select(Interview, Project)
        .join(Project, Interview.project_id == Project.id)
        .where(Interview.id == interview_id, project_scope_condition(user))
    )
    row = interview_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")

    interview, _project = row
    if interview.transcription_status != "completed":
        raise HTTPException(status_code=409, detail="Interview transcription is not completed")

    filters = [Fragment.interview_id == interview_id]
    if q:
        filters.append(Fragment.text.ilike(f"%{q}%"))
    if speaker_id:
        filters.append(Fragment.speaker_id == speaker_id)

    total_result = await db.execute(select(func.count()).select_from(Fragment).where(*filters))
    total_segments = total_result.scalar_one() or 0

    offset = (page - 1) * page_size
    seg_result = await db.execute(
        select(Fragment)
        .where(*filters)
        .order_by(Fragment.paragraph_index.asc().nullslast(), Fragment.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    segments = seg_result.scalars().all()

    return InterviewTranscriptResponse(
        interview=TranscriptInterviewResponse(
            id=interview.id,
            project_id=interview.project_id,
            participant_pseudonym=interview.participant_pseudonym,
            transcription_status=interview.transcription_status,
            transcription_method=interview.transcription_method,
            language=interview.language,
        ),
        pagination=TranscriptPaginationResponse(
            page=page,
            page_size=page_size,
            total_segments=total_segments,
            has_next=offset + len(segments) < total_segments,
        ),
        segments=[
            TranscriptSegmentResponse(
                fragment_id=s.id,
                paragraph_index=s.paragraph_index,
                speaker_id=s.speaker_id,
                text=s.text,
                start_offset=s.start_offset,
                end_offset=s.end_offset,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                created_at=s.created_at,
            )
            for s in segments
        ],
        full_text=interview.full_text if include_full_text else None,
    )


@router.post("/export", response_model=InterviewExportTaskCreated, status_code=202)
async def create_interview_export(
    request: InterviewExportRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _verify_project_ownership(request.project_id, user, db)

    if request.scope == "selected" and not request.interview_ids:
        raise HTTPException(status_code=422, detail="interview_ids is required when scope=selected")

    task_id = str(uuid.uuid4())
    _interview_export_tasks[task_id] = _new_export_task(task_id, request.project_id, user.user_uuid)
    await _persist_export_task(task_id)

    bg_task = asyncio.create_task(
        _run_interview_export_task(
            task_id=task_id,
            project_owner_id=(project.owner_id or user.user_uuid),
            project_id=request.project_id,
            request=request,
        )
    )
    _export_background_tasks.add(bg_task)
    bg_task.add_done_callback(_export_background_tasks.discard)

    return InterviewExportTaskCreated(
        task_id=task_id,
        status="queued",
        created_at=_interview_export_tasks[task_id]["created_at"],
    )


@router.get("/export/status/{task_id}", response_model=InterviewExportTaskStatusResponse)
async def get_interview_export_status(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    task = _interview_export_tasks.get(task_id) or await _restore_export_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("owner_id") != str(user.user_uuid):
        raise HTTPException(status_code=404, detail="Task not found")

    return InterviewExportTaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=int(task.get("progress", 0)),
        message=task.get("message"),
        result=task.get("result"),
    )


@router.get("/export/download/{task_id}")
async def get_interview_export_download(
    task_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    task = _interview_export_tasks.get(task_id) or await _restore_export_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("owner_id") != str(user.user_uuid):
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("status") != "completed" or not (task.get("result") or {}).get("download_url"):
        raise HTTPException(status_code=409, detail="Export is not completed")

    return {"download_url": task["result"]["download_url"]}


# Backward-compatible route kept at the end to avoid shadowing /export paths.
@router.get("/{project_id}", response_model=List[InterviewListItemResponse], include_in_schema=False)
async def list_interviews_legacy_path(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _list_interviews_impl(project_id=project_id, user=user, db=db)
