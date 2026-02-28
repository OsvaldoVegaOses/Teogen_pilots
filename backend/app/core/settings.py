import os
from pathlib import Path
from typing import Dict, List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


def _read_raw_env_value(key: str) -> str | None:
    value = os.getenv(key)
    if value is not None:
        return value
    fallback = _read_env_value(key)
    if fallback != "":
        return fallback
    return None


def _normalize_env(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"prod", "production", "live"}:
        return "production"
    if normalized in {"staging", "stage", "preprod", "uat"}:
        return "staging"
    if normalized in {"dev", "development", "local", "test"}:
        return "development"
    return normalized or "development"


class Settings(BaseSettings):
    PROJECT_NAME: str = "TheoGen"
    TESTING: bool = False
    APP_ENV: str = "development"
    THEORY_ENV_PROFILE: str = "auto"
    THEORY_ENV_PROFILE_EFFECTIVE: str = "development"
    THEORY_FAIL_STARTUP_ON_CONFIG_ERRORS: bool = False
    THEORY_CONFIG_ISSUES: List[str] = Field(default_factory=list)

    # Frontend URL
    FRONTEND_URL: str = ""

    # Microsoft Foundry / Azure OpenAI
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = "https://axial-resource.cognitiveservices.azure.com/"
    AZURE_OPENAI_API_VERSION: str = "2024-05-01-preview"

    # Model deployments
    MODEL_REASONING_ADVANCED: str = "gpt-5.2-chat"
    MODEL_REASONING_FAST: str = "gpt-5.2-chat"
    MODEL_REASONING_EFFICIENT: str = "gpt-5.2-chat"
    MODEL_CHAT: str = "gpt-5.2-chat"
    MODEL_ASSISTANT_PUBLIC: str = "gpt-5.2-chat"
    MODEL_ASSISTANT_AUTHENTICATED: str = "gpt-5.2-chat"
    MODEL_EMBEDDING: str = "text-embedding-3-large"
    MODEL_TRANSCRIPTION: str = "gpt-4o-transcribe-diarize"
    MODEL_CLAUDE_ADVANCED: str = "gpt-5.2-chat"
    MODEL_ROUTER: str = "gpt-5.2-chat"

    # Advanced options
    MODEL_KIMI: str = "gpt-5.2-chat"
    MODEL_DEEPSEEK: str = "gpt-5.2-chat"

    # Microsoft Foundry Agent Service
    AZURE_SUBSCRIPTION_ID: str = ""
    AZURE_RESOURCE_GROUP: str = ""
    FOUNDRY_PROJECT_NAME: str = ""

    # Azure PostgreSQL
    AZURE_PG_USER: str = ""
    AZURE_PG_PASSWORD: str = ""
    AZURE_PG_HOST: str = ""
    AZURE_PG_DATABASE: str = "theogen"
    ASSISTANT_PG_DATABASE: str = "theogen_assistant"
    ASSISTANT_DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Azure Storage
    AZURE_STORAGE_ACCOUNT: str = ""
    AZURE_STORAGE_KEY: str = ""
    AZURE_STORAGE_CONNECTION_STRING: str = ""

    # Speech
    AZURE_SPEECH_ENDPOINT: str = ""
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "westeurope"

    # Azure Redis + Celery
    AZURE_REDIS_HOST: str = ""
    AZURE_REDIS_KEY: str = ""
    REDIS_SSL_PORT: int = 6380
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    THEORY_USE_CELERY: bool = False
    ASSISTANT_TENANT_ADMIN_ROLES: str = "admin,ops,tenant_admin,platform_super_admin"

    # External managed services
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    QDRANT_URL: str
    QDRANT_API_KEY: str = ""

    # Runtime performance controls
    CODING_FRAGMENT_CONCURRENCY: int = 8
    THEORY_INTERVIEW_CONCURRENCY: int = 3
    THEORY_LOCAL_MAX_CONCURRENT_TASKS: int = 4
    THEORY_STATUS_POLL_HINT_SECONDS: int = 5
    THEORY_TASK_LOCK_TTL_SECONDS: int = 1800

    # External call timeouts / batching (prevent "stuck" tasks)
    AI_EMBEDDINGS_TIMEOUT_SECONDS: int = 120
    AI_EMBEDDINGS_MAX_RETRIES: int = 3
    AI_EMBEDDINGS_BATCH_SIZE: int = 64
    QDRANT_SEARCH_MAX_RETRIES: int = 3
    QDRANT_SEARCH_BACKOFF_SECONDS: float = 0.25
    HEALTHCHECK_TIMEOUT_SECONDS: int = 5
    HEALTHCHECK_DEPENDENCIES_KEY: str = ""
    THEORY_AUTOCODE_INTERVIEW_TIMEOUT_SECONDS: int = 3600
    CODING_QDRANT_UPSERT_TIMEOUT_SECONDS: int = 60
    CODING_NEO4J_SYNC_TIMEOUT_SECONDS: int = 120
    NEO4J_QUERY_TIMEOUT_SECONDS: int = 120

    # Context and budget controls
    THEORY_MAX_CATS_FOR_LLM: int = 50
    THEORY_MAX_EVIDENCE_FRAGS: int = 2
    THEORY_MAX_FRAG_CHARS: int = 400
    THEORY_MAX_NETWORK_TOP: int = 30
    # GraphRAG / evidence controls (MVP advanced)
    THEORY_USE_SUBGRAPH_EVIDENCE: bool = False
    THEORY_EVIDENCE_TARGET_MIN: int = 30
    THEORY_EVIDENCE_TARGET_MAX: int = 80
    THEORY_EVIDENCE_MIN_INTERVIEWS: int = 4
    THEORY_EVIDENCE_MAX_SHARE_PER_INTERVIEW: float = 0.4
    THEORY_EVIDENCE_INDEX_PERSIST_MAX: int = 1000
    THEORY_EVIDENCE_ID_CATALOG_MAX: int = 5000

    # Deterministic validation / traceability (MVP advanced)
    THEORY_USE_JUDGE: bool = False
    THEORY_JUDGE_WARN_ONLY: bool = False
    THEORY_JUDGE_ADAPTIVE_THRESHOLDS: bool = True
    THEORY_JUDGE_MIN_INTERVIEWS_FLOOR: int = 1
    THEORY_JUDGE_MIN_INTERVIEWS_RATIO: float = 0.6
    THEORY_JUDGE_BALANCE_MIN_EVIDENCE: int = 12
    THEORY_JUDGE_STRICT_COHORT_PERCENT: int = 0
    THEORY_JUDGE_STRICT_WINDOW: int = 5
    THEORY_JUDGE_STRICT_MIN_THEORIES: int = 3
    THEORY_JUDGE_STRICT_MAX_BAD_RUNS: int = 1
    THEORY_JUDGE_STRICT_PROMOTE_MAX_BAD_RUNS: int = 0
    THEORY_JUDGE_STRICT_DEGRADE_MIN_BAD_RUNS: int = 1
    THEORY_JUDGE_STRICT_COOLDOWN_RUNS: int = 3
    THEORY_JUDGE_STRICT_MAX_MODE_CHANGES_PER_WINDOW: int = 1
    THEORY_SYNC_CLAIMS_NEO4J: bool = False
    THEORY_SYNC_CLAIMS_QDRANT: bool = False
    THEORY_USE_DETERMINISTIC_GAPS: bool = False
    THEORY_USE_DETERMINISTIC_ROUTING: bool = False
    THEORY_MAX_CRITICAL_CATEGORIES: int = 10
    THEORY_MAX_CRITICAL_EDGES: int = 10
    THEORY_MAX_BRIDGE_CATEGORIES: int = 5
    THEORY_MAX_QDRANT_QUERIES: int = 60
    THEORY_QDRANT_RETRIEVAL_CONCURRENCY: int = 8
    THEORY_MATERIAL_QUERY_LIMIT: int = 3
    THEORY_LLM_MAX_OUTPUT_TOKENS: int = 8192
    THEORY_LLM_MAX_OUTPUT_TOKENS_LARGE: int = 16384
    THEORY_PROMPT_VERSION: str = "v2"
    THEORY_PIPELINE_MODE: str = "staged"
    THEORY_BUDGET_MARGIN_TOKENS: int = 2000
    THEORY_BUDGET_MAX_DEGRADATION_STEPS: int = 6
    THEORY_BUDGET_FALLBACK_MAX_CATS: int = 60
    THEORY_BUDGET_FALLBACK_MAX_FRAGS_PER_CAT: int = 3
    THEORY_BUDGET_FALLBACK_MAX_FRAG_CHARS: int = 900
    THEORY_BUDGET_FALLBACK_MAX_NETWORK_TOP: int = 60
    MODEL_CONTEXT_LIMIT_GPT_52_CHAT: int = 272000
    MODEL_CONTEXT_LIMIT_DEFAULT: int = 128000

    # Azure AD (Entra ID)
    AZURE_AD_TENANT_ID: str = ""
    AZURE_AD_CLIENT_ID: str = ""

    # Google Identity Services
    GOOGLE_CLIENT_ID: str = ""

    def _resolve_theory_profile(self) -> str:
        requested = str(self.THEORY_ENV_PROFILE or "auto").strip().lower()
        if requested in {"production", "staging", "development"}:
            return requested
        if requested in {"manual"}:
            return "manual"
        app_env = _normalize_env(self.APP_ENV)
        if app_env in {"production", "staging"}:
            return app_env
        return "development"

    def _apply_profile_defaults(self, profile: str) -> None:
        if profile == "manual":
            return

        defaults: Dict[str, bool] = {
            "development": {
                "THEORY_USE_JUDGE": False,
                "THEORY_JUDGE_WARN_ONLY": True,
                "THEORY_SYNC_CLAIMS_NEO4J": False,
                "THEORY_SYNC_CLAIMS_QDRANT": False,
            },
            "staging": {
                "THEORY_USE_JUDGE": True,
                "THEORY_JUDGE_WARN_ONLY": True,
                "THEORY_SYNC_CLAIMS_NEO4J": True,
                "THEORY_SYNC_CLAIMS_QDRANT": False,
            },
            "production": {
                "THEORY_USE_JUDGE": True,
                "THEORY_JUDGE_WARN_ONLY": False,
                "THEORY_SYNC_CLAIMS_NEO4J": True,
                "THEORY_SYNC_CLAIMS_QDRANT": True,
            },
        }.get(profile, {})

        for key, value in defaults.items():
            setattr(self, key, value)

    def _validate_theory_runtime_config(self, profile: str) -> List[str]:
        issues: List[str] = []
        if self.THEORY_JUDGE_WARN_ONLY and not self.THEORY_USE_JUDGE:
            issues.append("THEORY_JUDGE_WARN_ONLY=true requiere THEORY_USE_JUDGE=true.")
        if (self.THEORY_SYNC_CLAIMS_NEO4J or self.THEORY_SYNC_CLAIMS_QDRANT) and not self.THEORY_USE_JUDGE:
            issues.append("Claim sync requiere THEORY_USE_JUDGE=true para trazabilidad consistente.")

        if self.APP_ENV == "production" or profile == "production":
            if not self.THEORY_USE_JUDGE:
                issues.append("Produccion requiere THEORY_USE_JUDGE=true.")
            if self.THEORY_JUDGE_WARN_ONLY:
                issues.append("Produccion requiere THEORY_JUDGE_WARN_ONLY=false (modo estricto).")
            if not self.THEORY_SYNC_CLAIMS_NEO4J:
                issues.append("Produccion requiere THEORY_SYNC_CLAIMS_NEO4J=true.")
            if not self.THEORY_SYNC_CLAIMS_QDRANT:
                issues.append("Produccion requiere THEORY_SYNC_CLAIMS_QDRANT=true.")

        return issues

    def theory_runtime_config_summary(self) -> Dict[str, object]:
        return {
            "app_env": _normalize_env(self.APP_ENV),
            "profile_requested": str(self.THEORY_ENV_PROFILE or "auto").strip().lower() or "auto",
            "profile_effective": str(self.THEORY_ENV_PROFILE_EFFECTIVE or "development"),
            "use_judge": bool(self.THEORY_USE_JUDGE),
            "judge_warn_only": bool(self.THEORY_JUDGE_WARN_ONLY),
            "sync_claims_neo4j": bool(self.THEORY_SYNC_CLAIMS_NEO4J),
            "sync_claims_qdrant": bool(self.THEORY_SYNC_CLAIMS_QDRANT),
            "issues": list(self.THEORY_CONFIG_ISSUES or []),
            "ok": len(self.THEORY_CONFIG_ISSUES or []) == 0,
        }

    @model_validator(mode="after")
    def validate_required_integrations(self):
        self.APP_ENV = _normalize_env(self.APP_ENV)
        if not self.AZURE_SPEECH_ENDPOINT:
            self.AZURE_SPEECH_ENDPOINT = _read_env_value("AZURE_SPEECH_ENDPOINT")
        if not self.AZURE_SPEECH_KEY:
            self.AZURE_SPEECH_KEY = _read_env_value("AZURE_SPEECH_KEY")
        if not self.NEO4J_USER:
            self.NEO4J_USER = _read_env_value("NEO4J_USER") or _read_env_value("NEO4J_USERNAME")

        profile = self._resolve_theory_profile()
        self.THEORY_ENV_PROFILE_EFFECTIVE = profile
        self._apply_profile_defaults(profile)
        self.THEORY_CONFIG_ISSUES = self._validate_theory_runtime_config(profile)

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
