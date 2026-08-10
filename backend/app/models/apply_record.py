"""
投递记录表
记录每一次具体的投递动作和结果，防止重复投递，也用于统计分析
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class ApplyRecord(Base):
    __tablename__ = "apply_records"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    user_id = Column(Integer, ForeignKey("users.id"), index=True, comment="所属用户ID")
    task_id = Column(Integer, ForeignKey("apply_tasks.id"), index=True, comment="所属投递任务ID")
    platform = Column(String(20), index=True, comment="投递平台")

    # ===== 职位信息 =====
    job_id = Column(String(100), index=True, comment="职位ID（平台内部ID，用于去重）")
    job_title = Column(String(200), comment="职位名称")
    job_url = Column(String(500), comment="职位详情页URL")

    company_id = Column(String(100), index=True, comment="公司ID（平台内部ID）")
    company_name = Column(String(200), comment="公司名称")
    company_size = Column(String(100), comment="公司规模")
    company_industry = Column(String(200), comment="公司行业")

    salary_min = Column(Integer, comment="薪资下限（K）")
    salary_max = Column(Integer, comment="薪资上限（K）")
    salary_months = Column(Integer, comment="月薪数，如14薪")
    city = Column(String(100), comment="工作城市")
    area = Column(String(100), comment="工作区域")
    experience = Column(String(50), comment="经验要求文本")
    education = Column(String(50), comment="学历要求文本")

    # HR信息
    hr_name = Column(String(100), comment="HR姓名")
    hr_title = Column(String(100), comment="HR职位")
    hr_active_days = Column(Integer, comment="HR最近活跃天数（0=今天）")
    is_headhunter = Column(Integer, default=0, comment="是否猎头：0=否, 1=是")

    # ===== 投递状态 =====
    # pending=待处理, applying=投递中, success=成功, failed=失败, skipped=跳过, duplicate=重复
    status = Column(String(20), default="pending", index=True, comment="投递状态")
    applied_at = Column(DateTime, index=True, comment="实际投递时间")
    error_msg = Column(Text, comment="失败原因/跳过原因")

    # 打招呼消息（实际发送的内容）
    greeting_sent = Column(Text, comment="实际发送的打招呼消息")

    # 后续跟进状态
    follow_up_status = Column(String(20), default="none",
                              comment="跟进状态：none=无回复, replied=HR已回复, interviewed=已约面, rejected=被拒, offer=已拿offer")
    follow_up_remark = Column(Text, comment="跟进备注")

    extra_data = Column(JSON, comment="其他扩展字段JSON")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")

    # 关联关系
    user = relationship("User", back_populates="apply_records")
    apply_task = relationship("ApplyTask", back_populates="apply_records")
