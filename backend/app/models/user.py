"""
用户表
虽然目前是个人使用工具，但预留用户体系方便后续多账号/多用户扩展
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    username = Column(String(50), unique=True, index=True, nullable=False, comment="用户名")
    email = Column(String(100), unique=True, index=True, comment="邮箱")
    hashed_password = Column(String(255), comment="加密密码（个人使用可不设）")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")

    # 关联关系
    platform_sessions = relationship("PlatformSession", back_populates="user", cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    apply_tasks = relationship("ApplyTask", back_populates="user", cascade="all, delete-orphan")
    apply_records = relationship("ApplyRecord", back_populates="user", cascade="all, delete-orphan")
    filter_rules = relationship("FilterRule", back_populates="user", cascade="all, delete-orphan")
