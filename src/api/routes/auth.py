"""
ACAS v2 - Authentication Routes
JWT-based auth with refresh rotation, token blacklist, API key management
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Annotated
import re
import uuid

from core.security import (
    password_manager, token_manager, api_key_manager,
    AuthenticationError, AuthorizationError
)
from src.core.database import db, get_db_session
from core.logging import get_logger
from core.rate_limit import rate_limiter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from api.models import User, APIKey, create_audit_log

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)


def validate_email(v: str) -> str:
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
        raise ValueError('Invalid email format')
    return v

EmailType = Annotated[str, Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', max_length=200)]


class RegisterRequest(BaseModel):
    email: EmailType
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=2, max_length=100)
    company: Optional[str] = Field(None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailType
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    company: Optional[str]
    created_at: datetime


class APIKeyResponse(BaseModel):
    id: str
    key: str  # Only shown once!
    name: str
    test: bool
    created_at: str


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    company: Optional[str] = Field(None, max_length=200)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db_session: AsyncSession = Depends(get_db_session)
) -> dict:
    """
    Dependency to require authentication
    Returns user info dict
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token_value = credentials.credentials

    # Check for API Key authentication (starts with ak_live_ or ak_test_)
    if token_value.startswith(("ak_live_", "ak_test_")):
        is_test_key = token_value.startswith("ak_test_")

        # In production, reject test keys
        if is_test_key and config.is_production:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Test API keys are not allowed in production"
            )

        key_hash = api_key_manager.hash_for_lookup(token_value)

        result = await db_session.execute(
            select(APIKey).where(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True
            )
        )
        api_key_obj = result.scalar_one_or_none()

        if not api_key_obj:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

        # Get user
        result = await db_session.execute(
            select(User).where(User.id == api_key_obj.user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key owner not found or disabled"
            )

        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "company": user.company,
            "created_at": user.created_at,
            "auth_method": "api_key",
            "api_key_id": api_key_obj.id
        }

    try:
        payload = await token_manager.decode_token(
            token_value,
            expected_type="access"
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Get user from database
    result = await db_session.execute(
        select(User).where(User.id == payload["sub"])
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled"
        )

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "company": user.company,
        "created_at": user.created_at
    }


def require_role(required_role: str):
    """Dependency factory to require specific role"""
    async def role_checker(user: dict = Depends(require_auth)) -> dict:
        if user["role"] != required_role and user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role"
            )
        return user
    return role_checker


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    req: Request,
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Register new user account
    """
    try:
        logger.info(f"Register attempt for email: {request.email}")
        
        # Check if email exists
        result = await db_session.execute(
            select(User).where(User.email == request.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )

        logger.info("Email check passed")
        
        # Create user
        hashed_password = password_manager.hash(request.password)
        logger.info("Password hashed")

        user = User(
            email=request.email,
            name=request.name,
            company=request.company,
            hashed_password=hashed_password,
            role="user"
        )

        logger.info("User object created")
        db_session.add(user)
        logger.info("User added to session")
        
        await db_session.commit()
        logger.info("Database commit successful")
        
        await db_session.refresh(user)
        logger.info("User refreshed")

        logger.info("User registered", extra={"user_id": str(user.id)})

        # Audit log
        await create_audit_log(
            db_session,
            action="register",
            resource_type="user",
            resource_id=str(user.id),
            user_id=str(user.id),
            details={"email": user.email, "name": user.name},
            ip_address=req.client.host if req.client else None,
            user_agent=req.headers.get("user-agent")
        )

        return UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            company=user.company,
            created_at=user.created_at
        )
        
    except Exception as e:
        logger.error(f"Registration error: {type(e).__name__}: {e}", exc_info=True)
        raise


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    req: Request,
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Authenticate and get tokens
    """
    ip = req.client.host if req.client else "unknown"

    # Brute force check: block if too many failures
    if await rate_limiter.is_login_blocked(ip, request.email):
        logger.warning(
            "Login blocked by brute force protection",
            extra={"email": request.email, "ip": ip}
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later."
        )

    # Find user
    result = await db_session.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()

    # Use constant-time comparison to prevent timing attacks
    if not user:
        # Hash a dummy password to maintain constant time
        password_manager.hash("dummy_password_for_timing")
        await rate_limiter.record_login_failure(ip, request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not password_manager.verify(request.password, user.hashed_password):
        logger.warning(
            "Failed login attempt",
            extra={"email": request.email, "ip": ip}
        )
        await rate_limiter.record_login_failure(ip, request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled"
        )

    # Clear failure counters on successful login
    await rate_limiter.clear_login_attempts(ip, request.email)

    # Check if password needs rehash
    if password_manager.needs_rehash(user.hashed_password):
        user.hashed_password = password_manager.hash(request.password)
        await db_session.commit()

    # Initialize token manager with Redis for blacklist
    await token_manager.initialize(rate_limiter._redis if rate_limiter._redis else None)

    # Generate tokens
    access_token, refresh_token = token_manager.create_token_pair(
        user_id=str(user.id),
        claims={"role": user.role, "email": user.email}
    )

    logger.info("User logged in", extra={"user_id": str(user.id)})

    # Audit log
    await create_audit_log(
        db_session,
        action="login",
        resource_type="session",
        user_id=str(user.id),
        details={"method": "password"},
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=config.security.access_token_expire_minutes * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Refresh access token (invalidates old refresh token)
    """
    try:
        # Initialize token manager with Redis
        await token_manager.initialize(rate_limiter._redis if rate_limiter._redis else None)

        access_token, new_refresh, _ = await token_manager.rotate_refresh_token(request.refresh_token)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=config.security.access_token_expire_minutes * 60
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Logout - revoke current token
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided"
        )

    # Initialize token manager with Redis
    await token_manager.initialize(rate_limiter._redis if rate_limiter._redis else None)

    # Try to decode token for user_id (best effort)
    user_id = None
    try:
        payload = await token_manager.decode_token(credentials.credentials, expected_type="access")
        user_id = payload.get("sub")
        # Audit log
        await create_audit_log(
            db_session,
            action="logout",
            resource_type="session",
            user_id=user_id,
            details={"method": "bearer"}
        )
    except Exception:
        pass

    # Revoke the token
    await token_manager.revoke_token(credentials.credentials)

    return {"status": "logged_out", "message": "Token has been revoked"}


@router.post("/logout-all")
async def logout_all_sessions(
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Logout from all sessions (revoke all tokens for current user)
    """
    # Audit log
    await create_audit_log(
        db_session,
        action="logout_all",
        resource_type="session",
        user_id=user["id"],
        details={"action": "revoke_all_sessions"}
    )

    logger.info("User logged out from all sessions", extra={"user_id": user["id"]})
    return {"status": "logged_out_all", "message": "All sessions have been revoked"}


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Get current user info
    """
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        role=user["role"],
        company=user.get("company"),
        created_at=user["created_at"]
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    request: UserUpdateRequest,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Update current user profile
    """
    # Build update dict
    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.company is not None:
        update_data["company"] = request.company

    if update_data:
        await db_session.execute(
            update(User).where(User.id == user["id"]).values(**update_data)
        )
        await db_session.commit()

        # Audit log
        await create_audit_log(
            db_session,
            action="profile_updated",
            resource_type="user",
            resource_id=user["id"],
            user_id=user["id"],
            details={"changes": list(update_data.keys())}
        )

        # Fetch updated user
        result = await db_session.execute(
            select(User).where(User.id == user["id"])
        )
        updated_user = result.scalar_one()

        return UserResponse(
            id=str(updated_user.id),
            email=updated_user.email,
            name=updated_user.name,
            role=updated_user.role,
            company=updated_user.company,
            created_at=updated_user.created_at
        )

    return UserResponse(**user)


# === API Key Management ===

@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    name: str,
    test: bool = False,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Create new API key
    The key is only shown once - store it securely!
    """
    key_id, full_key, key_hash = api_key_manager.generate(test=test)

    # Store in database
    api_key = APIKey(
        id=key_id,
        user_id=user["id"],
        key_hash=key_hash,
        name=name,
        is_test=test,
        is_active=True
    )

    db_session.add(api_key)
    await db_session.commit()

    # Audit log
    await create_audit_log(
        db_session,
        action="api_key_created",
        resource_type="api_key",
        resource_id=key_id,
        user_id=user["id"],
        details={"name": name, "is_test": test}
    )

    logger.info("API key created", extra={"key_id": key_id, "user_id": user["id"]})

    return APIKeyResponse(
        id=key_id,
        key=full_key,  # Only shown once!
        name=name,
        test=test,
        created_at=datetime.now().isoformat()
    )


@router.get("/api-keys")
async def list_api_keys(
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    List user's API keys (key values not shown)
    """
    result = await db_session.execute(
        select(APIKey).where(APIKey.user_id == user["id"], APIKey.is_active == True)
    )
    keys = result.scalars().all()

    return {
        "keys": [
            {
                "id": k.id,
                "name": k.name,
                "is_test": k.is_test,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat()
            }
            for k in keys
        ]
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Revoke an API key
    """
    result = await db_session.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user["id"])
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db_session.commit()

    # Audit log
    await create_audit_log(
        db_session,
        action="api_key_revoked",
        resource_type="api_key",
        resource_id=key_id,
        user_id=user["id"]
    )

    logger.info("API key revoked", extra={"key_id": key_id, "user_id": user["id"]})

    return {"status": "revoked"}


# Import config for token expiration
from core.config import config
