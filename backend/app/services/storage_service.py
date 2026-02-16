from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from ..core.settings import settings
from datetime import datetime, timedelta
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class AzureBlobStorageService:
    CONTAINERS = {
        "audio": "theogen-audio",
        "documents": "theogen-documents",
        "exports": "theogen-exports",
        "backups": "theogen-backups",
    }

    def __init__(self):
        self.client = None
        self.local_mode = False
        if settings.AZURE_STORAGE_CONNECTION_STRING:
            self.client = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            )
        else:
            logger.warning("Azure Storage connection string not found. Local storage enabled.")
            self.local_mode = True

    async def upload_blob(self, container_key: str, blob_name: str, data: bytes) -> str:
        container_name = self.CONTAINERS.get(container_key, "misc")
        
        if self.local_mode:
            storage_path = Path("storage") / container_name
            storage_path.mkdir(parents=True, exist_ok=True)
            file_path = storage_path / blob_name.replace("/", "_")
            with open(file_path, "wb") as f:
                f.write(data)
            return f"local://{container_name}/{blob_name.replace('/', '_')}"

        if not self.client:
            raise Exception("Azure Storage client not initialized")
            
        container_client = self.client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(data, overwrite=True)
        return blob_client.url

    async def generate_sas_url(self, container_key: str, blob_name: str, expires_hours: int = 1) -> str:
        if self.local_mode:
            return f"local://{container_key}/{blob_name.replace('/', '_')}"

        if not settings.AZURE_STORAGE_ACCOUNT or not settings.AZURE_STORAGE_KEY:
            raise Exception("Azure Storage credentials for SAS generation not found")
            
        container_name = self.CONTAINERS.get(container_key)
        
        sas_token = generate_blob_sas(
            account_name=settings.AZURE_STORAGE_ACCOUNT,
            container_name=container_name,
            blob_name=blob_name,
            account_key=settings.AZURE_STORAGE_KEY,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=expires_hours)
        )
        return f"https://{settings.AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

storage_service = AzureBlobStorageService()
