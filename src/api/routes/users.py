"""
ACAS v2 - User Management Routes
Full implementation with admin and self-service endpoints
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from api.routes.auth import require_auth, require_role, UserResponse, UserUpdateRequest
from core.database import get_db_session
from core.logging import get_logger
from core.security import password_manager
from api.models import User, create_audit_log

logger = get_logger(__name__)
router = APIRouter()


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int


class AdminUserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = Field(None, pattern="^(user|analyst|admin)$")
    is_active: Optional[bool] = None


class UserRole(str):
    USER = "user"
    ANALYST = "analyst"
    ADMIN = "admin"
    VALID_ROLES = {"user", "analyst", "admin"}


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Get the currently authenticated user's profile.
    GET /users/me
    """
    result = await db_session.execute(
        select(User).where(User.id == user["id"])
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=str(db_user.id),
        email=db_user.email,
        name=db_user.name,
        role=db_user.role,
        company=db_user.company,
        created_at=db_user.created_at
    )


@router.get("/", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 50,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    List users (admin only)

    Supports filtering by:
    - role: user, analyst, admin
    - is_active: true/false
    - search: matches name or email
    """
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Build query
    query = select(User)
    count_query = select(func.count(User.id))

    # Apply filters
    if role and role in UserRole.VALID_ROLES:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (User.name.ilike(search_pattern)) | (User.email.ilike(search_pattern))
        )
        count_query = count_query.where(
            (User.name.ilike(search_pattern)) | (User.email.ilike(search_pattern))
        )

    # Get total count
    total_result = await db_session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db_session.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        users=[
            UserResponse(
                id=str(u.id),
                email=u.email,
                name=u.name,
                role=u.role,
                company=u.company,
                created_at=u.created_at
            )
            for u in users
        ],
        total=total,
        page=skip // limit + 1,
        page_size=limit
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Get user by ID
    - Users can view their own profile
    - Admins can view any profile
    """
    # Check permission
    if user["id"] != user_id and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Query user
    result = await db_session.execute(
        select(User).where(User.id == user_id)
    )
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=str(target_user.id),
        email=target_user.email,
        name=target_user.name,
        role=target_user.role,
        company=target_user.company,
        created_at=target_user.created_at
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: AdminUserUpdateRequest,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Update user profile
    - Users can update their own name/company
    - Admins can update any field including role and is_active
    """
    # Check permission
    is_self = user["id"] == user_id
    is_admin = user["role"] == "admin"

    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Query user
    result = await db_session.execute(
        select(User).where(User.id == user_id)
    )
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Build update data
    update_data = {}

    # Self can update name/company
    if request.name is not None:
        update_data["name"] = request.name

    if request.company is not None:
        update_data["company"] = request.company

    # Admin-only fields
    if is_admin:
        if request.role is not None:
            if request.role not in UserRole.VALID_ROLES:
                raise HTTPException(status_code=400, detail="Invalid role")
            update_data["role"] = request.role

        if request.is_active is not None:
            # Prevent admin from deactivating themselves
            if is_self and not request.is_active:
                raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
            update_data["is_active"] = request.is_active

    if update_data:
        await db_session.execute(
            update(User).where(User.id == user_id).values(**update_data)
        )
        await db_session.commit()
        await db_session.refresh(target_user)

        # Audit log
        await create_audit_log(
            db_session,
            action="user_updated",
            resource_type="user",
            resource_id=user_id,
            user_id=user["id"],
            details={"changes": list(update_data.keys()), "updated_by_role": user["role"]}
        )

        logger.info(
            "User updated",
            extra={
                "target_user_id": user_id,
                "updated_by": user["id"],
                "changes": list(update_data.keys())
            }
        )

    return UserResponse(
        id=str(target_user.id),
        email=target_user.email,
        name=target_user.name,
        role=target_user.role,
        company=target_user.company,
        created_at=target_user.created_at
    )


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Deactivate user account (soft delete)
    - Users can deactivate their own account
    - Admins can deactivate any account except their own
    """
    # Check permission
    is_self = user["id"] == user_id
    is_admin = user["role"] == "admin"

    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    # Prevent admin from deactivating themselves
    if is_self and is_admin:
        raise HTTPException(
            status_code=400,
            detail="Admins cannot deactivate their own account. Contact another admin."
        )

    # Deactivate user
    result = await db_session.execute(
        update(User).where(User.id == user_id).values(is_active=False)
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")

    await db_session.commit()

    # Audit log
    await create_audit_log(
        db_session,
        action="user_deactivated",
        resource_type="user",
        resource_id=user_id,
        user_id=user["id"],
        details={"deactivated_by": user["id"], "deactivated_by_role": user["role"]}
    )

    logger.info(
        "User deactivated",
        extra={"target_user_id": user_id, "deactivated_by": user["id"]}
    )

    return {"status": "deactivated", "message": "User account has been deactivated"}


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    user: dict = Depends(require_auth),
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Get user activity summary (admin only)
    """
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Query user
    result = await db_session.execute(
        select(User).where(User.id == user_id)
    )
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # In a full implementation, you'd query audit logs, forecast jobs, etc.
    # For now, return basic info
    return {
        "user_id": str(target_user.id),
        "email": target_user.email,
        "name": target_user.name,
        "role": target_user.role,
        "is_active": target_user.is_active,
        "created_at": target_user.created_at.isoformat(),
        "updated_at": target_user.updated_at.isoformat() if target_user.updated_at else None,
        "last_login": None,  # TODO: Track this
        "forecast_jobs_count": 0,  # TODO: Query ForecastJob
        "api_keys_count": len(target_user.api_keys) if target_user.api_keys else 0
    }
