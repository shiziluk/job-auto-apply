"""
平台会话表
存储各个招聘平台的登录Cookie、登录状态、账号信息等
参考 JobClaw 的 cookie_manager.py 设计，持久化保存避免每次重复登录
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class PlatformSession(Base):
    __tablename__ = "platform_sessions"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    user_id = Column(Integer, ForeignKey("users.id"), comment="所属用户ID")

    # 平台标识：boss=Boss直聘, lagou=拉勾, 51job=前程无忧, linkedin=领英
    platform = Column(String(20), index=True, nullable=False, comment="平台标识")
    platform_name = Column(String(50), comment="平台名称，如Boss直聘")

    # 登录信息
    cookies = Column(JSON, comment="Cookie JSON数组，Playwright格式")
    local_storage = Column(JSON, comment="浏览器LocalStorage")
    session_storage = Column(JSON, comment="浏览器SessionStorage")

    # 账号信息（可选，从页面抓取展示）
    account_name = Column(String(100), comment="账号昵称/姓名")
    account_avatar = Column(String(500), comment="账号头像URL")

    # 状态管理
    is_logged_in = Column(Boolean, default=False, index=True, comment="是否已登录")
    last_check_at = Column(DateTime, comment="上次检查Cookie有效性时间")
    last_login_at = Column(DateTime, comment="上次登录时间")
    login_expired_at = Column(DateTime, comment="预计过期时间")

    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")
    remark = Column(Text, comment="备注")

    # 关联关系
    user = relationship("User", back_populates="platform_sessions")
