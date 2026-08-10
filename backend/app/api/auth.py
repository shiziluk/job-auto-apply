"""
认证 API - 真实JWT登录
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.core.security import hash_password, verify_password, create_access_token
from app.api.deps import get_current_user
from app.schemas import ResponseModel

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ResponseModel)
def register(username: str, password: str, email: str = "", db: Session = Depends(get_db)):
    if not username or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名和密码必填")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名已存在")
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱已被注册")
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ResponseModel.success(message="注册成功", data={"user_id": user.id, "username": user.username})


@router.post("/login", response_model=ResponseModel)
def login(username: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已被禁用")
    token = create_access_token(data={"sub": user.id, "username": user.username})
    return ResponseModel.success(message="登录成功", data={
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        }
    })


@router.get("/me", response_model=ResponseModel)
def get_me(current_user: User = Depends(get_current_user)):
    return ResponseModel.success(data={
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
    })


@router.post("/change-password", response_model=ResponseModel)
def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.hashed_password or not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "原密码错误")
    current_user.hashed_password = hash_password(new_password)
    db.commit()
    return ResponseModel.success(message="密码修改成功")


@router.post("/init-admin", response_model=ResponseModel)
def init_admin(username: str = "admin", password: str = "admin123", db: Session = Depends(get_db)):
    """初始化管理员账号（仅用于首次部署）"""
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"用户 {username} 已存在")
    user = User(
        username=username,
        email=f"{username}@jobagent.local",
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ResponseModel.success(message="管理员初始化成功", data={"user_id": user.id})
