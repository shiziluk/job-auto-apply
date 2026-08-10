"""
简历相关Schema
"""
import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ResumeBase(BaseModel):
    resume_name: str = Field(description="简历名称")
    target_position: Optional[str] = Field(default=None, description="目标岗位")
    target_city: Optional[str] = Field(default=None, description="目标城市")
    salary_min: Optional[int] = Field(default=None, description="期望最低薪资K")
    salary_max: Optional[int] = Field(default=None, description="期望最高薪资K")
    years_experience: Optional[int] = Field(default=None, description="工作年限")
    is_default: bool = Field(default=False, description="是否默认简历")
    remark: Optional[str] = Field(default=None, description="备注")


class ResumeCreate(ResumeBase):
    user_id: Optional[int] = Field(default=None, description="用户ID（后端自动从登录态填充）")
    file_name: str = Field(description="原始文件名")
    file_path: str = Field(description="存储路径")
    file_size: int = Field(description="文件大小字节")
    file_type: str = Field(description="文件类型pdf/doc/docx")


class ResumeUpdate(BaseModel):
    resume_name: Optional[str] = None
    target_position: Optional[str] = None
    target_city: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    years_experience: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None


class ResumeInfo(ResumeBase):
    id: int
    user_id: int
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    is_active: bool = True
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class ResumeUploadResponse(BaseModel):
    file_name: str = Field(description="原始文件名")
    saved_path: str = Field(description="保存后的路径")
    file_size: int = Field(description="文件大小")
    file_type: str = Field(description="文件类型")
