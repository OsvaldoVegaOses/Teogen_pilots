from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "TheoGen"
    
    # Microsoft Foundry / Azure OpenAI API v1
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    # New in 2025: api_version is less critical with /v1/ endpoint but still used in AzureOpenAI client
    AZURE_OPENAI_API_VERSION: str = "2024-10-21" 
    
    # Model Deployments (Excat names from your Foundry Portal)
    MODEL_REASONING_ADVANCED: str = "gpt-5.2-chat"
    MODEL_REASONING_FAST: str = "o3-mini" # Maintain for future or swap if needed
    MODEL_REASONING_EFFICIENT: str = "o4-mini"
    MODEL_CHAT: str = "gpt-4o"
    MODEL_EMBEDDING: str = "text-embedding-3-large"
    MODEL_TRANSCRIPTION: str = "gpt-4o-transcribe-diarize"
    MODEL_CLAUDE_ADVANCED: str = "claude-3-5-sonnet-20241022"
    MODEL_ROUTER: str = "model-router"
    
    # Advanced Options (Kimi and DeepSeek identified in your portal)
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
    
    # Azure Storage
    AZURE_STORAGE_ACCOUNT: str = ""
    AZURE_STORAGE_KEY: str = ""
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    
    # Foundry Tools (Speech)
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "westeurope"
    
    # Azure Redis (v7.4)
    AZURE_REDIS_HOST: str = ""
    AZURE_REDIS_KEY: str = ""
    
    # External Managed
    NEO4J_URI: str = ""
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    
    # Azure AD (Entra ID)
    AZURE_AD_TENANT_ID: str = ""
    AZURE_AD_CLIENT_ID: str = ""
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
