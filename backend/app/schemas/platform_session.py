"""
平台会话相关Schema
"""
import datetime
from typing import Optional, Any, List
from pydantic import BaseModel, Field


# ============ 基础信息 ============
class PlatformSessionBase(BaseModel):
    platform: str = Field(description="平台标识：boss/lagou/51job")
    platform_name: Optional[str] = Field(default=None, description="平台名称")
    account_name: Optional[str] = Field(default=None, description="账号昵称")
    account_avatar: Optional[str] = Field(default=None, description="账号头像")


class PlatformSessionCreate(PlatformSessionBase):
    user_id: int = Field(description="用户ID")
    cookies: Optional[Any] = Field(default=None, description="Cookie JSON")
    local_storage: Optional[Any] = Field(default=None, description="LocalStorage")
    session_storage: Optional[Any] = Field(default=None, description="SessionStorage")


class PlatformSessionUpdate(BaseModel):
    cookies: Optional[Any] = Field(default=None)
    local_storage: Optional[Any] = Field(default=None)
    session_storage: Optional[Any] = Field(default=None)
    is_logged_in: Optional[bool] = Field(default=None)
    account_name: Optional[str] = Field(default=None)
    account_avatar: Optional[str] = Field(default=None)
    last_check_at: Optional[datetime.datetime] = Field(default=None)
    login_expired_at: Optional[datetime.datetime] = Field(default=None)
    remark: Optional[str] = Field(default=None)


class PlatformSessionInfo(PlatformSessionBase):
    id: int
    user_id: int
    is_logged_in: bool
    last_check_at: Optional[datetime.datetime] = None
    last_login_at: Optional[datetime.datetime] = None
    login_expired_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    remark: Optional[str] = None

    class Config:
        from_attributes = True


# ============ 登录操作相关 ============
class LoginStartRequest(BaseModel):
    """开始登录请求"""
    platform: str = Field(default="boss", description="目标平台")
    user_id: int = Field(default=1, description="用户ID，个人使用默认1")


class LoginStatusResponse(BaseModel):
    """登录状态响应"""
    task_id: str = Field(description="登录任务ID，用于轮询状态")
    status: str = Field(description="状态：waiting=等待扫码, logged_in=已登录, failed=失败, timeout=超时")
    session_id: Optional[int] = Field(default=None, description="登录成功后的会话ID")
    qr_code_url: Optional[str] = Field(default=None, description="二维码图片URL（如果有）")
    message: Optional[str] = Field(default=None, description="提示消息")
