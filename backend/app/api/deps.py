"""
FastAPI API 通用依赖
- JWT Token 解析
- 分页参数
- 文件校验
"""
import os
import math
from typing import Optional, TypeVar, Generic, List, Tuple

from fastapi import Depends, HTTPException, status, UploadFile, File, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from app.database import get_db
from app.models import User
from app.config import settings
from app.core.security import decode_access_token

T = TypeVar("T")


# ============ 分页参数解析 ============
def get_page_params(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
) -> Tuple[int, int]:
    return page, page_size


def paginate_query(query, db: Session, page: int, page_size: int) -> Tuple[List, int, int]:
    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total, total_pages


def make_page_result(items: List, total: int, page: int, page_size: int) -> dict:
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ============ JWT 鉴权 ============
def _extract_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """严格鉴权：必须带有效JWT才能访问"""
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录，请先登录")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token无效或已过期")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token格式错误")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")
    return user


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """宽松鉴权：有有效JWT就返回用户，没有就返回None"""
    token = _extract_token(authorization)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id), User.is_active == True).first()


# ============ 文件校验 ============
ALLOWED_RESUME_TYPES = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}
ALLOWED_RESUME_EXT = {"pdf", "doc", "docx"}


def validate_resume_file(file: UploadFile = File(...)) -> UploadFile:
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ALLOWED_RESUME_EXT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式 .{ext}，仅支持: {', '.join(ALLOWED_RESUME_EXT)}"
        )
    return file


def ensure_upload_dir():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    return settings.UPLOAD_DIR
