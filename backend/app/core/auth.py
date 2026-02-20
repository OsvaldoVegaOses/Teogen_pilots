"""
Azure AD (Entra ID) JWT Token Validation for FastAPI.

This module provides:
- JWKS (JSON Web Key Set) based token validation
- Automatic key caching and refresh
- FastAPI dependency injection for protected routes
- User identity extraction from validated tokens

Security flow:
1. Frontend obtains an ID token via MSAL loginRedirect
2. Frontend sends it as `Authorization: Bearer <token>` 
3. This module validates the token signature against Azure AD's public keys
4. Extracts user identity (oid, email, name) for data isolation
"""

import logging
import time
from typing import Optional
from uuid import UUID, NAMESPACE_URL, uuid5

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from .settings import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

TENANT_ID = settings.AZURE_AD_TENANT_ID
CLIENT_ID = settings.AZURE_AD_CLIENT_ID

# Azure AD OpenID Connect endpoints
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
JWKS_URL = f"{AUTHORITY}/discovery/v2.0/keys"
ISSUER_V1 = f"https://sts.windows.net/{TENANT_ID}/"
ISSUER_V2 = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

# ──────────────────────────────────────────────
# JWKS Key Cache
# ──────────────────────────────────────────────

_jwks_cache: Optional[dict] = None
_jwks_cache_timestamp: float = 0
JWKS_CACHE_DURATION = 3600  # 1 hour


async def _get_signing_keys() -> dict:
    """
    Fetch and cache Azure AD's public signing keys (JWKS).
    Keys are cached for 1 hour to avoid repeated network calls.
    """
    global _jwks_cache, _jwks_cache_timestamp

    now = time.time()
    if _jwks_cache and (now - _jwks_cache_timestamp) < JWKS_CACHE_DURATION:
        return _jwks_cache

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(JWKS_URL, timeout=10)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cache_timestamp = now
            logger.info("JWKS keys refreshed from Azure AD")
            return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS keys: {e}")
        if _jwks_cache:
            # Return stale cache rather than failing completely
            logger.warning("Using stale JWKS cache")
            return _jwks_cache
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to validate authentication keys",
        )


def _find_key(jwks: dict, kid: str) -> Optional[dict]:
    """Find the specific key matching the token's Key ID (kid)."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


# ──────────────────────────────────────────────
# User Model
# ──────────────────────────────────────────────


class CurrentUser(BaseModel):
    """Represents the authenticated user extracted from the JWT token."""

    oid: str  # Azure AD Object ID — unique and immutable
    email: Optional[str] = None
    name: Optional[str] = None
    preferred_username: Optional[str] = None
    tenant_id: Optional[str] = None

    @property
    def user_uuid(self) -> UUID:
        """
        Converts token user identifier to UUID for DB operations.
        If the claim is not a canonical UUID (common with some `sub` values),
        derive a stable UUIDv5 so project ownership remains deterministic.
        """
        try:
            return UUID(self.oid)
        except (ValueError, TypeError):
            stable_uuid = uuid5(NAMESPACE_URL, f"theogen-user:{self.oid}")
            logger.warning(
                "Token user identifier is not UUID. Using stable UUIDv5 fallback.",
                extra={"raw_user_id": self.oid, "stable_user_uuid": str(stable_uuid)},
            )
            return stable_uuid


# ──────────────────────────────────────────────
# FastAPI Dependencies
# ──────────────────────────────────────────────

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> CurrentUser:
    """
    FastAPI dependency that validates the Azure AD Bearer token
    and returns the authenticated user.

    Usage in endpoints:
        @router.get("/protected")
        async def my_endpoint(user: CurrentUser = Depends(get_current_user)):
            print(user.oid, user.email)
    """
    # ── Guard: Check configuration ──
    if not TENANT_ID or not CLIENT_ID:
        logger.error("AZURE_AD_TENANT_ID or AZURE_AD_CLIENT_ID not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured on server",
        )

    # ── Guard: Check token presence ──
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # 1. Decode the token header (without verification) to get the Key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header missing key ID (kid)",
            )

        # 2. Fetch the matching signing key from Azure AD
        jwks = await _get_signing_keys()
        signing_key = _find_key(jwks, kid)

        if not signing_key:
            # Key not found — maybe keys rotated? Force refresh and retry
            global _jwks_cache_timestamp
            _jwks_cache_timestamp = 0
            jwks = await _get_signing_keys()
            signing_key = _find_key(jwks, kid)

            if not signing_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token signing key not recognized",
                )

        # 3. Validate the token signature, expiration, audience, and issuer
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=[ISSUER_V1, ISSUER_V2],
            options={
                "verify_at_hash": False,  # ID tokens from SPA may not include at_hash
            },
        )

        # 4. Extract user identity from claims
        oid = payload.get("oid") or payload.get("sub")
        if not oid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user identifier (oid/sub)",
            )

        return CurrentUser(
            oid=oid,
            email=payload.get("email") or payload.get("preferred_username"),
            name=payload.get("name"),
            preferred_username=payload.get("preferred_username"),
            tenant_id=payload.get("tid"),
        )

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise  # Re-raise our own HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Optional[CurrentUser]:
    """
    Like get_current_user, but returns None instead of 401 if no token is present.
    Useful for endpoints that work for both authenticated and anonymous users.
    """
    if not credentials:
        return None
    return await get_current_user(credentials)
