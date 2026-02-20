
import httpx
import logging
from urllib.parse import urlparse
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..core.settings import settings
from .azure_openai import foundry_openai

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
        self.region = settings.AZURE_SPEECH_REGION

        if not self.speech_key:
            # Not raising error here allows fallback-only mode if configured
            logger.warning("AZURE_SPEECH_KEY not set. Primary transcription (axial-speech) will fail.")

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
        Primary Method: Azure AI Speech (Fast Transcription API).
        Supports direct URL ingestion (no download needed).
        """
        # API Endpoint for 2024-05-15-preview (Batch Transcription)
        endpoint = (
            f"https://{self.region}.api.cognitive.microsoft.com"
            f"/speechtotext/transcriptions:transcribe?api-version=2024-05-15-preview" 
        )

        headers = {
            "Ocp-Apim-Subscription-Key": self.speech_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        payload = {
            "contentUrls": [audio_blob_url],
            "locale": language,
            "displayName": "TheoGen Transcription",
            "model": None, # Use default model
            "properties": {
                "diarizationEnabled": True,
                "wordLevelTimestampsEnabled": True,
                "punctuationMode": "DictatedAndAutomatic",
                "profanityFilterMode": "Masked"
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            # Extract combined text
            combined = result.get("combinedPhrases", [{}])[0].get("text", "")
            
            return {
                "full_text": combined,
                "segments": result.get("phrases", []),
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
        filename = f"interview{ext}"
        language_code = (language or "es").split("-")[0]

        response = await client.audio.transcriptions.create(
            file=(filename, audio_content),
            model=settings.MODEL_TRANSCRIPTION,
            language=language_code,
        )

        transcript_text = getattr(response, "text", None) or ""
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
