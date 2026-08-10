"""
过滤规则表（黑白名单）
参考 boss_push 的筛选设计：
- 白名单：公司名/职位名包含则优先投递
- 黑名单：公司名/职位名包含则直接跳过
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class FilterRule(Base):
    __tablename__ = "filter_rules"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    user_id = Column(Integer, ForeignKey("users.id"), index=True, comment="所属用户ID")

    # 规则类型：whitelist=白名单, blacklist=黑名单
    rule_type = Column(String(20), index=True, nullable=False, comment="规则类型：whitelist/blacklist")

    # 匹配字段：company=公司名, job=职位名, job_desc=职位描述, all=全部字段
    match_field = Column(String(20), default="all", index=True, comment="匹配字段")

    # 匹配模式：contains=包含(模糊匹配), exact=精确匹配, regex=正则匹配
    match_mode = Column(String(20), default="contains", comment="匹配模式")

    # 匹配内容，多个关键词用逗号分隔（contains模式下是或的关系）
    keywords = Column(String(1000), nullable=False, comment="匹配关键词，多个逗号分隔")

    rule_name = Column(String(200), comment="规则名称，方便管理")
    is_enabled = Column(Integer, default=1, index=True, comment="是否启用：1=启用, 0=禁用")
    priority = Column(Integer, default=0, comment="优先级，数字越大越先匹配")

    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")
    remark = Column(Text, comment="备注")

    # 关联关系
    user = relationship("User", back_populates="filter_rules")
