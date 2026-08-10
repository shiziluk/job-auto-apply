"""
简历管理 API
接口列表：
- POST   /api/resume/upload    上传简历文件
- POST   /api/resume           创建简历记录（关联上传的文件）
- GET    /api/resumes          简历列表
- GET    /api/resume/{id}      简历详情
- PUT    /api/resume/{id}      更新简历
- DELETE /api/resume/{id}      删除简历
- POST   /api/resume/{id}/default 设为默认
"""
import os
import uuid
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import Resume, User
from app.schemas import (
    ResumeCreate, ResumeUpdate, ResumeInfo, ResumeUploadResponse,
    ResponseModel, PageResult,
)
from app.api.deps import (
    get_current_user, validate_resume_file, ensure_upload_dir,
    get_page_params, paginate_query, make_page_result,
)

router = APIRouter(tags=["简历管理"])


# ========== 上传简历文件 ==========
@router.post("/resume/upload", response_model=ResponseModel[ResumeUploadResponse])
async def upload_resume(
    file: UploadFile = Depends(validate_resume_file),
    user: User = Depends(get_current_user),
):
    """上传简历文件到服务器"""
    upload_dir = ensure_upload_dir()
    ext = file.filename.rsplit(".", 1)[-1].lower()
    # 生成不冲突的文件名
    saved_name = f"resume_{user.id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"
    saved_path = os.path.join(upload_dir, saved_name)

    # 写入文件
    size = 0
    with open(saved_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunk
            size += len(chunk)
            f.write(chunk)

    if size == 0:
        os.remove(saved_path) if os.path.exists(saved_path) else None
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上传的文件为空")
    if size > settings.MAX_UPLOAD_SIZE:
        os.remove(saved_path) if os.path.exists(saved_path) else None
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"文件过大 ({size//1024}KB)，上限 {settings.MAX_UPLOAD_SIZE//1024//1024}MB")

    # 保存相对路径（方便后续通过/uploads访问）
    rel_path = saved_name
    return ResponseModel.success(data=ResumeUploadResponse(
        file_name=file.filename,
        saved_path=rel_path,
        file_size=size,
        file_type=ext,
    ), message="上传成功")


# ========== 创建简历记录 ==========
@router.post("/resume", response_model=ResponseModel[ResumeInfo])
def create_resume(
    data: ResumeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """将上传的文件注册为简历条目（附带名称、目标岗位等信息）"""
    data.user_id = user.id
    # 若设为默认，先把其他默认取消
    if data.is_default:
        db.query(Resume).filter(Resume.user_id == user.id).update({"is_default": False})
    obj = Resume(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return ResponseModel.success(data=obj, message="创建成功")


# ========== 简历列表 ==========
@router.get("/resumes", response_model=ResponseModel[PageResult[ResumeInfo]])
def list_resumes(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page_params=Depends(get_page_params),
):
    page, page_size = page_params
    q = db.query(Resume).filter(Resume.user_id == user.id)
    if is_active is not None:
        q = q.filter(Resume.is_active == is_active)
    q = q.order_by(Resume.is_default.desc(), Resume.created_at.desc())
    items, total, _ = paginate_query(q, db, page, page_size)
    return ResponseModel.success(data=make_page_result(items, total, page, page_size))


# ========== 简历详情 ==========
@router.get("/resume/{resume_id}", response_model=ResponseModel[ResumeInfo])
def get_resume(resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "简历不存在")
    return ResponseModel.success(data=obj)


# ========== 更新简历 ==========
@router.put("/resume/{resume_id}", response_model=ResponseModel[ResumeInfo])
def update_resume(
    resume_id: int,
    data: ResumeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "简历不存在")
    update_data = data.model_dump(exclude_unset=True)
    # 设为默认的处理
    if update_data.get("is_default"):
        db.query(Resume).filter(Resume.user_id == user.id, Resume.id != resume_id).update({"is_default": False})
    for k, v in update_data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return ResponseModel.success(data=obj, message="更新成功")


# ========== 删除简历 ==========
@router.post("/resume/{resume_id}/delete", response_model=ResponseModel)
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "简历不存在")
    # 尝试删除物理文件
    if obj.file_path:
        full_path = os.path.join(settings.UPLOAD_DIR, obj.file_path)
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass
    db.delete(obj)
    db.commit()
    return ResponseModel.success(message="删除成功")


# ========== 设为默认 ==========
@router.post("/resume/{resume_id}/default", response_model=ResponseModel[ResumeInfo])
def set_default_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "简历不存在")
    db.query(Resume).filter(Resume.user_id == user.id).update({"is_default": False})
    obj.is_default = True
    db.commit()
    db.refresh(obj)
    return ResponseModel.success(data=obj, message="已设为默认简历")
