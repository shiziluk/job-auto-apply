"""
简历表
管理用户上传的简历文件（PDF/Word等），支持多份简历切换投递
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    user_id = Column(Integer, ForeignKey("users.id"), index=True, comment="所属用户ID")

    resume_name = Column(String(200), nullable=False, comment="简历名称，如'后端开发3年经验版'")
    file_name = Column(String(255), comment="原始文件名")
    file_path = Column(String(500), comment="存储路径（相对uploads目录）")
    file_size = Column(Integer, comment="文件大小（字节）")
    file_type = Column(String(50), comment="文件类型：pdf/doc/docx")

    # 简历基本信息（可选，从文件解析或手动填写，方便后续匹配）
    target_position = Column(String(200), comment="目标岗位")
    target_city = Column(String(100), comment="目标城市")
    salary_min = Column(Integer, comment="期望最低薪资（K）")
    salary_max = Column(Integer, comment="期望最高薪资（K）")
    years_experience = Column(Integer, comment="工作年限")

    is_default = Column(Boolean, default=False, index=True, comment="是否默认简历")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="上传时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")
    remark = Column(Text, comment="备注")

    # 关联关系
    user = relationship("User", back_populates="resumes")
    apply_tasks = relationship("ApplyTask", back_populates="resume")
