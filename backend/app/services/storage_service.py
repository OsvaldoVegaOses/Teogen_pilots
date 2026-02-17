from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from ..core.settings import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AzureBlobStorageService:
    """Azure Blob Storage service — no local fallback.
    
    Requires AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT + AZURE_STORAGE_KEY.
    """

    CONTAINERS = {
        "audio": "theogen-audio",
        "documents": "theogen-documents",
        "exports": "theogen-exports",
        "backups": "theogen-backups",
    }

    def __init__(self):
        self.client = None

        if settings.AZURE_STORAGE_CONNECTION_STRING:
            self.client = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            )
        elif settings.AZURE_STORAGE_ACCOUNT and settings.AZURE_STORAGE_KEY:
            # Build connection string from account + key
            conn_str = (
                f"DefaultEndpointsProtocol=https;"
                f"AccountName={settings.AZURE_STORAGE_ACCOUNT};"
                f"AccountKey={settings.AZURE_STORAGE_KEY};"
                f"EndpointSuffix=core.windows.net"
            )
            self.client = BlobServiceClient.from_connection_string(conn_str)
        else:
            raise RuntimeError(
                "Azure Storage credentials not found. "
                "Set AZURE_STORAGE_CONNECTION_STRING or both AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_KEY."
            )

    async def upload_blob(self, container_key: str, blob_name: str, data: bytes) -> str:
        """Upload blob and return its URL."""
        container_name = self.CONTAINERS.get(container_key, "misc")

        container_client = self.client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        await blob_client.upload_blob(data, overwrite=True)
        return blob_client.url

    async def generate_sas_url(self, container_key: str, blob_name: str, expires_hours: int = 1) -> str:
        """Generate a SAS URL for reading a blob."""
        if not settings.AZURE_STORAGE_ACCOUNT or not settings.AZURE_STORAGE_KEY:
            raise RuntimeError("Azure Storage credentials for SAS generation not found")

        container_name = self.CONTAINERS.get(container_key)
        if not container_name:
            raise ValueError(f"Unknown container key: {container_key}")

        sas_token = generate_blob_sas(
            account_name=settings.AZURE_STORAGE_ACCOUNT,
            container_name=container_name,
            blob_name=blob_name,
            account_key=settings.AZURE_STORAGE_KEY,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=expires_hours),
        )
        return f"https://{settings.AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

storage_service = AzureBlobStorageService()
