
import httpx
import logging
import subprocess
import tempfile
import uuid
from urllib.parse import urlparse
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from azure.core.credentials import AzureKeyCredential
from azure.ai.transcription.aio import TranscriptionClient
from azure.ai.transcription.models import TranscriptionOptions

from ..core.settings import settings
from .azure_openai import foundry_openai
from .storage_service import storage_service

logger = logging.getLogger(__name__)

class FoundryTranscriptionService:
    """Transcription using Foundry Tools 2025 (Primary: Azure Speech, Fallback: GPT-4o Audio).
    
    Robustness Features:
    - Retries with exponential backoff for network errors (via 'tenacity')
    - Automatic fallback to GPT-4o if Azure Speech fails completely
    - Atomic status handling (managed by caller/background task logic)
    """

    def __init__(self):
        self.speech_key = settings.AZURE_SPEECH_KEY
        self.speech_endpoint = settings.AZURE_SPEECH_ENDPOINT
        self.region = settings.AZURE_SPEECH_REGION
        self.max_primary_audio_seconds = 900
        self.max_fallback_audio_seconds = 1450
        self.chunk_seconds = 900
        self.primary_preprocess_exts = {".m4a", ".mp4", ".aac", ".webm", ".ogg", ".mp3"}

        if not self.speech_key:
            # Not raising error here allows fallback-only mode if configured
            logger.warning("AZURE_SPEECH_KEY not set. Primary transcription (axial-speech) will fail.")

    @staticmethod
    def _audio_duration_seconds(file_path: Path) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())

    @staticmethod
    def _convert_to_wav(input_path: Path, output_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    def _split_wav_into_chunks(self, wav_path: Path, output_dir: Path) -> list[Path]:
        chunk_pattern = output_dir / "chunk_%03d.wav"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(wav_path),
            "-f",
            "segment",
            "-segment_time",
            str(self.chunk_seconds),
            "-c",
            "copy",
            str(chunk_pattern),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return sorted(output_dir.glob("chunk_*.wav"))

    @staticmethod
    def _speech_extract(result) -> tuple[str, list[dict]]:
        combined_phrases = getattr(result, "combined_phrases", None) or []
        combined = combined_phrases[0].text if combined_phrases else ""

        raw_phrases = getattr(result, "phrases", None) or []
        segments = []
        for phrase in raw_phrases:
            segments.append(
                {
                    "text": getattr(phrase, "text", ""),
                    "speaker": getattr(phrase, "speaker", None),
                    "offsetMilliseconds": getattr(phrase, "offset_milliseconds", None),
                    "durationMilliseconds": getattr(phrase, "duration_milliseconds", None),
                }
            )
        return combined, segments

    async def _speech_transcribe_chunked_from_bytes(
        self,
        client: TranscriptionClient,
        audio_content: bytes,
        source_ext: str,
        language: str,
        audio_blob_url: str,
    ) -> tuple[str, list[dict]]:
        parsed = urlparse(audio_blob_url)
        blob_parts = parsed.path.lstrip("/").split("/", 2)
        project_prefix = blob_parts[1] if len(blob_parts) > 1 else "unknown-project"

        with tempfile.TemporaryDirectory(prefix="theogen-speech-primary-") as tmp_dir:
            tmp = Path(tmp_dir)
            input_file = tmp / f"input{source_ext or '.bin'}"
            input_file.write_bytes(audio_content)

            wav_file = tmp / "normalized.wav"
            self._convert_to_wav(input_file, wav_file)

            chunk_dir = tmp / "chunks"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunks = self._split_wav_into_chunks(wav_file, chunk_dir)
            if not chunks:
                chunks = [wav_file]

            options = TranscriptionOptions(locales=[language])
            joined_text_parts: list[str] = []
            joined_segments: list[dict] = []

            logger.info("Speech primary preprocessing generated %s chunk(s)", len(chunks))

            for idx, chunk_path in enumerate(chunks):
                chunk_blob = (
                    f"{project_prefix}/speech-primary-chunks/"
                    f"{uuid.uuid4()}-{idx:03d}.wav"
                )
                chunk_bytes = chunk_path.read_bytes()
                await storage_service.upload_blob("audio", chunk_blob, chunk_bytes, content_type="audio/wav")
                chunk_sas = await storage_service.generate_sas_url("audio", chunk_blob, expires_hours=2)

                logger.info("Speech primary transcribing chunk %s/%s", idx + 1, len(chunks))
                chunk_result = await client.transcribe_from_url(chunk_sas, options=options)
                chunk_text, chunk_segments = self._speech_extract(chunk_result)
                if chunk_text:
                    joined_text_parts.append(chunk_text)
                if chunk_segments:
                    joined_segments.extend(chunk_segments)

            return "\n".join(joined_text_parts).strip(), joined_segments

    async def _transcribe_audio_bytes(
        self,
        client,
        audio_bytes: bytes,
        extension: str,
        language_code: str,
    ) -> str:
        response = await client.audio.transcriptions.create(
            file=(f"interview{extension}", audio_bytes),
            model=settings.MODEL_TRANSCRIPTION,
            language=language_code,
            chunking_strategy="auto",
        )
        return (getattr(response, "text", None) or "").strip()

    async def _transcribe_large_audio_with_chunking(
        self,
        client,
        audio_content: bytes,
        source_ext: str,
        language_code: str,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="theogen-audio-") as tmp_dir:
            tmp = Path(tmp_dir)
            input_file = tmp / f"input{source_ext or '.bin'}"
            input_file.write_bytes(audio_content)

            wav_file = tmp / "normalized.wav"
            self._convert_to_wav(input_file, wav_file)

            chunk_dir = tmp / "chunks"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunks = self._split_wav_into_chunks(wav_file, chunk_dir)
            if not chunks:
                chunks = [wav_file]

            chunk_texts: list[str] = []
            for chunk_path in chunks:
                chunk_bytes = chunk_path.read_bytes()
                part_text = await self._transcribe_audio_bytes(
                    client=client,
                    audio_bytes=chunk_bytes,
                    extension=".wav",
                    language_code=language_code,
                )
                if part_text:
                    chunk_texts.append(part_text)

            return "\n".join(chunk_texts).strip()

    async def transcribe_interview(self, audio_blob_url: str, language: str = "es-CL") -> dict:
        """
        Main pipeline:
        1. Try Azure Speech (Primary)
        2. On failure, Try GPT-4o Audio (Fallback)
        """
        try:
            logger.info(f"Attempting primary transcription (Azure Speech) for {audio_blob_url}")
            return await self.transcribe_fast(audio_blob_url, language)
        except Exception as e:
            logger.warning(f"Primary transcription failed: {e}. Falling back to GPT-4o.")
            try:
                return await self.transcribe_gpt4o_audio(audio_blob_url, language)
            except Exception as fe:
                logger.error(f"Fallback transcription (GPT-4o) also failed: {fe}")
                raise RuntimeError("All transcription methods failed.") from fe

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def transcribe_fast(self, audio_blob_url: str, language: str = "es-CL") -> dict:
        """
        Primary Method: Azure AI Speech (Fast Transcription SDK).
        Uses transcribe_from_url for direct Blob/SAS ingestion.
        """
        parsed = urlparse(audio_blob_url)
        ext = Path(parsed.path).suffix.lower() or ".wav"

        speech_base = (self.speech_endpoint or "").rstrip("/")
        if not speech_base:
            speech_base = f"https://{self.region}.api.cognitive.microsoft.com"

        logger.info(
            "Speech primary start | endpoint=%s | locale=%s | ext=%s",
            speech_base,
            language,
            ext,
        )

        credential = AzureKeyCredential(self.speech_key)
        options = TranscriptionOptions(locales=[language])

        async with TranscriptionClient(endpoint=speech_base, credential=credential) as client:
            use_preprocess = False
            duration = None
            audio_content = None
            try:
                async with httpx.AsyncClient(timeout=120.0) as http_client:
                    audio_response = await http_client.get(audio_blob_url)
                    audio_response.raise_for_status()
                    audio_content = audio_response.content

                with tempfile.TemporaryDirectory(prefix="theogen-primary-duration-") as tmp_dir:
                    source = Path(tmp_dir) / f"source{ext}"
                    source.write_bytes(audio_content)
                    duration = self._audio_duration_seconds(source)

                use_preprocess = ext in self.primary_preprocess_exts or duration > self.max_primary_audio_seconds
                logger.info(
                    "Speech primary analyze | duration=%.2fs | preprocess=%s",
                    duration,
                    use_preprocess,
                )
            except Exception as e:
                logger.warning("Speech primary duration analysis unavailable (%s). Using direct URL mode.", e)

            if use_preprocess and audio_content:
                combined, segments = await self._speech_transcribe_chunked_from_bytes(
                    client=client,
                    audio_content=audio_content,
                    source_ext=ext,
                    language=language,
                    audio_blob_url=audio_blob_url,
                )
            else:
                result = await client.transcribe_from_url(audio_blob_url, options=options)
                combined, segments = self._speech_extract(result)

            return {
                "full_text": combined,
                "segments": segments,
                "language": language,
                "method": "axial-speech",
                "status": "completed",
            }

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=10),
        reraise=True
    )
    async def transcribe_gpt4o_audio(self, audio_blob_url: str, language: str) -> dict:
        """
        Fallback Method: Azure OpenAI Audio Transcriptions API.
        Deployment: MODEL_TRANSCRIPTION (ej. gpt-4o-transcribe-diarize)
        """
        client = foundry_openai.azure_client 
        if not client:
             raise RuntimeError("Foundry Azure OpenAI client not initialized")

        logger.info(f"Executing fallback transcription with {settings.MODEL_TRANSCRIPTION}")

        # 1. Download audio from Blob Storage
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            audio_response = await http_client.get(audio_blob_url)
            audio_response.raise_for_status()
            audio_content = audio_response.content

        # 2. Use Audio Transcriptions API (not chat completions)
        parsed = urlparse(audio_blob_url)
        ext = Path(parsed.path).suffix.lower() or ".wav"
        language_code = (language or "es").split("-")[0]

        transcript_text = ""
        try:
            with tempfile.TemporaryDirectory(prefix="theogen-duration-") as tmp_dir:
                input_path = Path(tmp_dir) / f"source{ext}"
                input_path.write_bytes(audio_content)
                duration = self._audio_duration_seconds(input_path)

            logger.info("Fallback analyze | duration=%.2fs | ext=%s", duration, ext)

            if duration > self.max_fallback_audio_seconds:
                logger.info(
                    "Fallback audio duration %.2fs exceeds limit %.2fs. Applying automatic chunking.",
                    duration,
                    self.max_fallback_audio_seconds,
                )
                transcript_text = await self._transcribe_large_audio_with_chunking(
                    client=client,
                    audio_content=audio_content,
                    source_ext=ext,
                    language_code=language_code,
                )
            else:
                transcript_text = await self._transcribe_audio_bytes(
                    client=client,
                    audio_bytes=audio_content,
                    extension=ext,
                    language_code=language_code,
                )
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as media_err:
            logger.warning(f"Audio preprocessing unavailable ({media_err}). Trying direct fallback transcription.")
            transcript_text = await self._transcribe_audio_bytes(
                client=client,
                audio_bytes=audio_content,
                extension=ext,
                language_code=language_code,
            )

        if not transcript_text:
            raise RuntimeError("Fallback transcription returned empty text")

        return {
            "full_text": transcript_text or "",
            "segments": [], 
            "language": language,
            "method": "gpt-4o-fallback",
            "status": "completed"
        }

transcription_service = FoundryTranscriptionService()
