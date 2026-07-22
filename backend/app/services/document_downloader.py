"""Download official documents from sources."""
import httpx
import hashlib
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings


class DocumentDownloader:
    """Download and store documents."""

    CHUNK_SIZE = 8192
    TIMEOUT = 30.0

    @staticmethod
    async def download_file(url: str, max_size_mb: int = 25) -> bytes | None:
        """Download file from URL with size limits."""
        max_bytes = max_size_mb * 1024 * 1024
        
        try:
            async with httpx.AsyncClient(
                timeout=DocumentDownloader.TIMEOUT,
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        return None
                    
                    data = b""
                    async for chunk in response.aiter_bytes(chunk_size=DocumentDownloader.CHUNK_SIZE):
                        data += chunk
                        if len(data) > max_bytes:
                            return None
                    
                    return data if data else None
        except Exception:
            return None

    @staticmethod
    def compute_checksum(data: bytes) -> str:
        """Compute SHA256 checksum of file content."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    async def save_file(filename: str, data: bytes) -> str:
        """Save file to raw data storage and return path."""
        import os
        storage_path = settings.raw_document_storage_path or "data/raw"
        os.makedirs(storage_path, exist_ok=True)
        
        filepath = os.path.join(storage_path, filename)
        with open(filepath, "wb") as f:
            f.write(data)
        
        return filepath
