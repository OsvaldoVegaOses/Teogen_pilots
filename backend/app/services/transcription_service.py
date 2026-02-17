import httpx
from ..core.settings import settings
from .azure_openai import foundry_openai
import logging

logger = logging.getLogger(__name__)

class FoundryTranscriptionService:
    """Transcription using Foundry Tools 2025 (Fast Transcription + Diarization).
    
    No mock/local fallback — requires Azure Speech credentials.
    """

    def __init__(self):
        self.speech_key = settings.AZURE_SPEECH_KEY
        self.region = settings.AZURE_SPEECH_REGION

        if not self.speech_key:
            raise RuntimeError(
                "AZURE_SPEECH_KEY is required. "
                "TheoGen does not support mock transcription."
            )

    async def transcribe_interview(self, audio_blob_url: str, language: str = "es-CL") -> dict:
        """
        Transcription pipeline: try axial-speech first, then gpt-4o-transcribe-diarize.
        """
        try:
            logger.info(f"Attempting primary transcription with axial-speech for {audio_blob_url}")
            return await self.transcribe_fast(audio_blob_url, language)
        except Exception as e:
            logger.warning(f"Primary transcription (axial-speech) failed: {e}. Falling back to GPT-4o.")
            try:
                return await self.transcribe_diarize(audio_blob_url)
            except Exception as fe:
                logger.error(f"Fallback transcription also failed: {fe}")
                raise RuntimeError("All transcription methods failed") from fe

    async def transcribe_fast(self, audio_blob_url: str, language: str = "es-CL") -> dict:
        """Fast Transcription API 2025 — pre-recorded interviews (axial-speech)."""
        endpoint = (
            f"https://{self.region}.api.cognitive.microsoft.com"
            f"/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
        )

        headers = {
            "Ocp-Apim-Subscription-Key": self.speech_key,
            "Content-Type": "application/json",
        }

        payload = {
            "contentUrls": [audio_blob_url],
            "locale": language,
            "diarizationEnabled": True,
            "wordLevelTimestampsEnabled": True,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code != 200:
                logger.error(f"axial-speech API error: {response.text}")
                raise RuntimeError(f"axial-speech failed with status {response.status_code}")

            result = response.json()

        return {
            "full_text": result["combinedPhrases"][0]["display"],
            "segments": result["phrases"],
            "language": language,
            "method": "axial-speech",
            "status": "completed",
        }

    async def transcribe_diarize(self, audio_blob_url: str) -> dict:
        """Fallback: gpt-4o-transcribe-diarize for high-fidelity qualitative analysis."""
        if not foundry_openai.client:
            raise RuntimeError("Foundry AI client not initialized for fallback transcription")

        logger.info(f"Executing fallback diarization with {settings.MODEL_TRANSCRIPTION}")

        # TODO: Implement real gpt-4o-transcribe-diarize API call
        # This requires downloading the audio and sending it via the OpenAI audio API.
        raise NotImplementedError(
            "gpt-4o-transcribe-diarize fallback is not yet implemented. "
            "Ensure axial-speech is properly configured."
        )

transcription_service = FoundryTranscriptionService()
