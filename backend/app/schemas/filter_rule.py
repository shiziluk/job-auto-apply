"""
过滤规则（黑白名单）相关Schema
"""
import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FilterRuleBase(BaseModel):
    rule_type: str = Field(description="规则类型：whitelist白名单/blacklist黑名单")
    match_field: str = Field(default="all", description="匹配字段：company/job/job_desc/all")
    match_mode: str = Field(default="contains", description="匹配模式：contains/exact/regex")
    keywords: str = Field(description="关键词，多个逗号分隔")
    rule_name: Optional[str] = Field(default=None, description="规则名称")
    is_enabled: int = Field(default=1, description="1启用/0禁用")
    priority: int = Field(default=0, description="优先级，越大越先匹配")
    remark: Optional[str] = Field(default=None)


class FilterRuleCreate(FilterRuleBase):
    user_id: int


class FilterRuleUpdate(BaseModel):
    rule_type: Optional[str] = None
    match_field: Optional[str] = None
    match_mode: Optional[str] = None
    keywords: Optional[str] = None
    rule_name: Optional[str] = None
    is_enabled: Optional[int] = None
    priority: Optional[int] = None
    remark: Optional[str] = None


class FilterRuleInfo(FilterRuleBase):
    id: int
    user_id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
