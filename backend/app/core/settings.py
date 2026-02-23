from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from pathlib import Path

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _read_env_value(key: str) -> str:
    if not ROOT_ENV_FILE.exists():
        return ""
    for raw_line in ROOT_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        env_key, env_value = line.split("=", 1)
        if env_key.strip() == key:
            return env_value.strip().strip('"').strip("'")
    return ""

class Settings(BaseSettings):
    PROJECT_NAME: str = "TheoGen"
    TESTING: bool = False
    
    # Frontend URL
    FRONTEND_URL: str = ""
    
    # Microsoft Foundry / Azure OpenAI API v1
    AZURE_OPENAI_API_KEY: str = ""  # Tu clave de acceso
    AZURE_OPENAI_ENDPOINT: str = "https://axial-resource.cognitiveservices.azure.com/"  # Tu endpoint
    # New in 2025: api_version is less critical with /v1/ endpoint but still used in AzureOpenAI client
    AZURE_OPENAI_API_VERSION: str = "2024-05-01-preview" 
    
    # Model Deployments (Exact names from your Foundry Portal)
    # gpt-5.2-chat: 4250 RPM / 425K TPM — primary reasoning model
    # DeepSeek-V3.2-Speciale: 500 RPM — returns empty choices via /v1/ endpoint; kept for direct use only
    MODEL_REASONING_ADVANCED: str = "gpt-5.2-chat"
    MODEL_REASONING_FAST: str = "gpt-5.2-chat"
    MODEL_REASONING_EFFICIENT: str = "gpt-5.2-chat"
    MODEL_CHAT: str = "gpt-5.2-chat"
    MODEL_EMBEDDING: str = "text-embedding-3-large"
    MODEL_TRANSCRIPTION: str = "gpt-4o-transcribe-diarize"
    MODEL_CLAUDE_ADVANCED: str = "Kimi-K2.5"  # Fallback para claude_analysis()
    MODEL_ROUTER: str = "model-router"
    
    # Advanced Options (Models identified in your portal)
    MODEL_KIMI: str = "Kimi-K2.5"
    MODEL_DEEPSEEK: str = "DeepSeek-V3.2-Speciale"
    
    # Microsoft Foundry Agent Service
    AZURE_SUBSCRIPTION_ID: str = ""
    AZURE_RESOURCE_GROUP: str = ""
    FOUNDRY_PROJECT_NAME: str = ""
    
    # Azure PostgreSQL
    AZURE_PG_USER: str = ""
    AZURE_PG_PASSWORD: str = ""
    AZURE_PG_HOST: str = ""
    AZURE_PG_DATABASE: str = "theogen"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    
    # Azure Storage
    AZURE_STORAGE_ACCOUNT: str = ""
    AZURE_STORAGE_KEY: str = ""
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    
    # Foundry Tools (Speech)
    AZURE_SPEECH_ENDPOINT: str = ""
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "westeurope"
    
    # Azure Redis (v7.4)
    AZURE_REDIS_HOST: str = ""
    AZURE_REDIS_KEY: str = ""
    REDIS_SSL_PORT: int = 6380
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    THEORY_USE_CELERY: bool = False
    
    # External Managed
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    
    QDRANT_URL: str
    QDRANT_API_KEY: str = ""

    # Runtime performance controls
    CODING_FRAGMENT_CONCURRENCY: int = 8
    THEORY_INTERVIEW_CONCURRENCY: int = 3
    THEORY_STATUS_POLL_HINT_SECONDS: int = 5
    THEORY_TASK_LOCK_TTL_SECONDS: int = 1800
    
    # Azure AD (Entra ID)
    AZURE_AD_TENANT_ID: str = ""
    AZURE_AD_CLIENT_ID: str = ""
    
    @model_validator(mode="after")
    def validate_required_integrations(self):
        if not self.AZURE_SPEECH_ENDPOINT:
            self.AZURE_SPEECH_ENDPOINT = _read_env_value("AZURE_SPEECH_ENDPOINT")
        if not self.AZURE_SPEECH_KEY:
            self.AZURE_SPEECH_KEY = _read_env_value("AZURE_SPEECH_KEY")
        if not self.NEO4J_USER:
            self.NEO4J_USER = _read_env_value("NEO4J_USER") or _read_env_value("NEO4J_USERNAME")

        if self.TESTING:
            return self

        required = {
            "NEO4J_URI": self.NEO4J_URI,
            "NEO4J_USER": self.NEO4J_USER,
            "NEO4J_PASSWORD": self.NEO4J_PASSWORD,
            "QDRANT_URL": self.QDRANT_URL,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")
        return self

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        extra="ignore",
        env_ignore_empty=True,
    )

settings = Settings()
