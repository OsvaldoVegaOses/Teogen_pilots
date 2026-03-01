"""
Multi-provider JWT Token Validation for FastAPI.

Supported identity providers:
- Azure AD (Entra ID): organizational accounts
- Microsoft Personal Accounts (MSA): hotmail/outlook/live
- Google Identity Services: Google accounts via direct id_token

Security flow:
1. Frontend obtains an ID token from the provider
2. Frontend sends it as `Authorization: Bearer <token>`
3. This module inspects the unverified `iss` claim to route to the correct validator
4. Validates the token signature against the provider's public JWKS
5. Extracts user identity (oid/sub, email, name) for data isolation
"""

import logging
import time
from typing import Any, Optional
from uuid import UUID, NAMESPACE_URL, uuid5

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from .settings import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

TENANT_ID = settings.AZURE_AD_TENANT_ID
CLIENT_ID = settings.AZURE_AD_CLIENT_ID

# Azure AD OpenID Connect endpoints
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
# Use 'common' JWKS endpoint so keys from both org and personal account tenants are available
JWKS_URL = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
ISSUER_V1 = f"https://sts.windows.net/{TENANT_ID}/"
ISSUER_V2 = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
# Personal Microsoft Account (MSA) tokens are issued by the consumers tenant (fixed ID)
MSA_ISSUER_V2 = "https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0"

# Google Identity Services endpoints
GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = "https://accounts.google.com"

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


# ── Google JWKS cache ──
_google_jwks_cache: Optional[dict] = None
_google_jwks_cache_timestamp: float = 0


async def _get_google_signing_keys() -> dict:
    """Fetch and cache Google's public signing keys (JWKS)."""
    global _google_jwks_cache, _google_jwks_cache_timestamp

    now = time.time()
    if _google_jwks_cache and (now - _google_jwks_cache_timestamp) < JWKS_CACHE_DURATION:
        return _google_jwks_cache

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(GOOGLE_JWKS_URL, timeout=10)
            response.raise_for_status()
            _google_jwks_cache = response.json()
            _google_jwks_cache_timestamp = now
            logger.info("JWKS keys refreshed from Google")
            return _google_jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch Google JWKS keys: {e}")
        if _google_jwks_cache:
            logger.warning("Using stale Google JWKS cache")
            return _google_jwks_cache
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


def _as_str_list(value: Any) -> list[str]:
    """Normalizes token claims that may arrive as string or array."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


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
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)

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

    def has_any_role(self, role_names: set[str]) -> bool:
        expected = {role.strip().lower() for role in role_names if role and role.strip()}
        if not expected:
            return False
        current = {role.strip().lower() for role in self.roles if role and role.strip()}
        return bool(current.intersection(expected))

    @property
    def effective_tenant_id(self) -> str:
        """
        Stable tenant scope used by RBAC enforcement.
        - Uses token `tid` when present.
        - Falls back to a synthetic per-user tenant for providers without tenant claim.
        """
        tenant = str(self.tenant_id or "").strip()
        if tenant:
            return tenant
        return f"user:{self.user_uuid}"


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

        # 2. Peek at the issuer claim (unverified) to route to the correct provider
        unverified_claims = jwt.get_unverified_claims(token)
        token_issuer = unverified_claims.get("iss", "")

        if token_issuer == GOOGLE_ISSUER:
            # ── Google Identity Services path ──
            if not GOOGLE_CLIENT_ID:
                logger.warning("Google token received but GOOGLE_CLIENT_ID not configured")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google authentication not configured on server",
                )

            google_jwks = await _get_google_signing_keys()
            signing_key = _find_key(google_jwks, kid)

            if not signing_key:
                global _google_jwks_cache_timestamp
                _google_jwks_cache_timestamp = 0
                google_jwks = await _get_google_signing_keys()
                signing_key = _find_key(google_jwks, kid)
                if not signing_key:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token signing key not recognized",
                    )

            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=GOOGLE_CLIENT_ID,
                issuer=GOOGLE_ISSUER,
                options={"verify_at_hash": False},
            )

            oid = payload.get("sub")
            if not oid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing user identifier (sub)",
                )

            return CurrentUser(
                oid=oid,
                email=payload.get("email"),
                name=payload.get("name"),
                preferred_username=payload.get("email"),
                tenant_id=None,
                roles=_as_str_list(payload.get("roles")),
                groups=_as_str_list(payload.get("groups")),
            )

        else:
            # ── Azure AD / MSA path ──
            jwks = await _get_signing_keys()
            signing_key = _find_key(jwks, kid)

            if not signing_key:
                global _jwks_cache_timestamp
                _jwks_cache_timestamp = 0
                jwks = await _get_signing_keys()
                signing_key = _find_key(jwks, kid)

                if not signing_key:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token signing key not recognized",
                    )

            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=CLIENT_ID,
                issuer=[ISSUER_V1, ISSUER_V2, MSA_ISSUER_V2],
                options={
                    "verify_at_hash": False,  # ID tokens from SPA may not include at_hash
                },
            )

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
                roles=_as_str_list(payload.get("roles")),
                groups=_as_str_list(payload.get("groups")),
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
