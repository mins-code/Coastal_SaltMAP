import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# In production, this should be securely loaded from your .env file
# e.g., os.environ.get("GOV_API_KEY", "saltmap_demo_key")
GOV_API_KEY = "saltmap-gov-key-2026"

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """
    Dependency to validate the X-API-Key header for protected endpoints.
    """
    if api_key_header == GOV_API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate API Key. Please provide a valid X-API-Key header.",
    )
