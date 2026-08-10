"""
投递任务表
保存用户创建的每一次投递任务的配置：搜索关键词、筛选条件、投递模式等
相当于JobClaw的profiles/me.yaml + 命令行参数，只不过我们存在数据库里
"""
import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class ApplyTask(Base):
    __tablename__ = "apply_tasks"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    user_id = Column(Integer, ForeignKey("users.id"), index=True, comment="所属用户ID")
    resume_id = Column(Integer, ForeignKey("resumes.id"), index=True, comment="使用的简历ID")

    task_name = Column(String(200), nullable=False, comment="任务名称，如'Python后端深圳投递'")
    platform = Column(String(20), default="boss", index=True, comment="投递平台")

    # ===== 搜索条件 =====
    search_keywords = Column(String(500), comment="搜索关键词，多个用逗号分隔，如'Python,后端,开发'")
    city_code = Column(String(50), comment="城市编码（Boss直聘内部编码）")
    city_name = Column(String(100), comment="城市名称")

    # 薪资范围（K）
    salary_min = Column(Integer, comment="最低薪资")
    salary_max = Column(Integer, comment="最高薪资")

    # 经验要求：0=不限, 1=应届, 2=1年以内, 3=1-3年, 4=3-5年, 5=5-10年, 6=10年以上
    experience = Column(Integer, default=0, comment="工作经验要求")
    # 学历要求：0=不限, 1=大专, 2=本科, 3=硕士, 4=博士
    education = Column(Integer, default=0, comment="学历要求")

    # 公司规模：空=不限, 多个用逗号分隔
    # 1=0-20人, 2=20-99人, 3=100-499人, 4=500-999人, 5=1000-9999人, 6=10000人以上
    company_scales = Column(String(100), comment="公司规模编码，多个逗号分隔")

    # 行业筛选，多个逗号分隔
    industries = Column(String(500), comment="行业编码，多个逗号分隔")

    # 休息制度筛选：双休/大小周/单休（JSON数组）
    rest_policy = Column(JSON, comment="休息制度筛选：双休/大小周/单休（可多选）")

    # ===== 投递模式 =====
    # auto=全自动符合条件就投, semi=半自动展示给用户确认后再投
    apply_mode = Column(String(20), default="semi", comment="投递模式：auto/semi")
    # 单次最大处理职位数
    max_jobs_per_run = Column(Integer, default=30, comment="单次运行最大处理数")
    # 每日投递上限（覆盖全局配置）
    daily_limit = Column(Integer, comment="每日投递上限，空则用全局配置")

    # 打招呼消息模板（参考JobClaw，支持$company/$title/$name变量）
    greeting_template = Column(Text, comment="打招呼消息模板")

    # 过滤条件（boss_push的经验）
    skip_inactive_days = Column(Integer, default=7, comment="跳过HR多少天未活跃的岗位")
    skip_headhunter = Column(Boolean, default=True, comment="是否跳过猎头岗位")
    skip_internship = Column(Boolean, default=True, comment="是否跳过实习岗位")

    # 任务状态
    status = Column(String(20), default="draft", index=True,
                    comment="任务状态：draft=草稿, running=运行中, paused=暂停, completed=完成, failed=失败")
    # 最近一次运行的运行时进度（total/current/success/failed/skipped/results等）
    progress = Column(JSON, comment="最近一次运行的运行时进度JSON")
    last_run_at = Column(DateTime, comment="上次运行时间")
    total_applied = Column(Integer, default=0, comment="累计已投递数")
    total_success = Column(Integer, default=0, comment="累计投递成功数")
    total_failed = Column(Integer, default=0, comment="累计投递失败数")

    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="更新时间")
    remark = Column(Text, comment="备注")

    # 关联关系
    user = relationship("User", back_populates="apply_tasks")
    resume = relationship("Resume", back_populates="apply_tasks")
    apply_records = relationship("ApplyRecord", back_populates="apply_task", cascade="all, delete-orphan")
