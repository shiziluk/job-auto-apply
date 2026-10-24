"""
投递任务 & 投递记录 相关Schema
"""
import datetime
from typing import Optional, List, Any, Union
from pydantic import BaseModel, Field


# ============ 投递任务 ============
class ApplyTaskBase(BaseModel):
    task_name: str = Field(description="任务名称")
    platform: str = Field(default="boss", description="投递平台")
    resume_id: Optional[int] = Field(default=None, description="使用的简历ID")

    # 搜索条件
    search_keywords: Optional[str] = Field(default=None, description="搜索关键词，多逗号分隔")
    city_code: Optional[Union[str, List[str]]] = Field(default=None, description="城市编码，支持多个（多城市会逐个搜索后合并），空=全国")
    city_name: Optional[str] = Field(default=None, description="城市名称")
    salary_min: Optional[int] = Field(default=None, description="最低薪资K")
    salary_max: Optional[int] = Field(default=None, description="最高薪资K")
    experience: int = Field(default=0, description="经验要求：0不限1应届2-1年3-3年4-5年5-10年6-10+")
    education: int = Field(default=0, description="学历要求：0不限1大专2本科3硕士4博士")
    company_scales: Optional[str] = Field(default=None, description="公司规模编码，逗号分隔")
    industries: Optional[str] = Field(default=None, description="行业编码，逗号分隔")
    rest_policy: Optional[list] = Field(default=None, description="休息制度筛选：双休/大小周/单休（可多选）")

    # 投递模式
    apply_mode: str = Field(default="semi", description="投递模式：semi半自动/auto全自动")
    max_jobs_per_run: int = Field(default=30, description="单次最大处理数")
    daily_limit: Optional[int] = Field(default=None, description="每日投递上限")
    rest_policy: Optional[List[str]] = Field(default=None, description="休息制度终检：双休/大小周/单休，空=不检查")
    greeting_template: Optional[str] = Field(default=None, description="打招呼消息模板")

    # 过滤
    skip_inactive_days: int = Field(default=7, description="跳过N天未活跃HR")
    skip_headhunter: bool = Field(default=True, description="是否跳过猎头")
    skip_internship: bool = Field(default=True, description="是否跳过实习")
    remark: Optional[str] = Field(default=None, description="备注")


class ApplyTaskCreate(ApplyTaskBase):
    user_id: int = Field(description="用户ID")


class ApplyTaskUpdate(BaseModel):
    task_name: Optional[str] = None
    resume_id: Optional[int] = None
    search_keywords: Optional[str] = None
    city_code: Optional[str] = None
    city_name: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    experience: Optional[int] = None
    education: Optional[int] = None
    company_scales: Optional[str] = None
    industries: Optional[str] = None
    rest_policy: Optional[list] = None
    apply_mode: Optional[str] = None
    max_jobs_per_run: Optional[int] = None
    daily_limit: Optional[int] = None
    greeting_template: Optional[str] = None
    skip_inactive_days: Optional[int] = None
    skip_headhunter: Optional[bool] = None
    skip_internship: Optional[bool] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class ApplyTaskInfo(ApplyTaskBase):
    id: int
    user_id: int
    status: str = "draft"
    last_run_at: Optional[datetime.datetime] = None
    total_applied: int = 0
    total_success: int = 0
    total_failed: int = 0
    progress: Optional[dict] = Field(default=None, description="最近一次运行的进度JSON")
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


# ============ 投递记录 ============
class ApplyRecordBase(BaseModel):
    job_id: str = Field(description="职位平台ID")
    job_title: Optional[str] = Field(default=None, description="职位名称")
    job_url: Optional[str] = Field(default=None, description="详情URL")
    company_id: Optional[str] = Field(default=None, description="公司ID")
    company_name: Optional[str] = Field(default=None, description="公司名称")
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    city: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    hr_name: Optional[str] = None
    is_headhunter: int = 0


class ApplyRecordInfo(ApplyRecordBase):
    id: int
    user_id: int
    task_id: Optional[int] = None
    platform: Optional[str] = None
    company_size: Optional[str] = None
    company_industry: Optional[str] = None
    salary_months: Optional[int] = None
    area: Optional[str] = None
    hr_title: Optional[str] = None
    hr_active_days: Optional[int] = None
    status: str = "pending"
    applied_at: Optional[datetime.datetime] = None
    error_msg: Optional[str] = None
    greeting_sent: Optional[str] = None
    follow_up_status: str = "none"
    follow_up_remark: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


# ============ 运行时的职位对象（非DB，用于前后端交互）============
class JobItem(BaseModel):
    """从平台抓取到的职位对象，用于展示给用户勾选投递"""
    platform: str = Field(description="平台")
    job_id: str = Field(description="职位ID")
    job_title: str = Field(description="职位名称")
    job_url: str = Field(description="详情页链接")
    company_id: Optional[str] = Field(default=None, description="公司ID")
    company_name: Optional[str] = Field(default=None, description="公司名称")
    company_size: Optional[str] = Field(default=None)
    company_industry: Optional[str] = Field(default=None)
    salary_min: Optional[int] = Field(default=None)
    salary_max: Optional[int] = Field(default=None)
    salary_text: Optional[str] = Field(default=None, description="薪资原文，如15-25K·14薪")
    city: Optional[str] = Field(default=None)
    area: Optional[str] = Field(default=None)
    experience: Optional[str] = Field(default=None)
    education: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=[], description="职位标签列表")
    rest_policy: Optional[str] = Field(default=None, description="休息制度：双休/大小周/单休")
    hr_name: Optional[str] = Field(default=None)
    hr_title: Optional[str] = Field(default=None)
    hr_active_days: Optional[int] = Field(default=None, description="HR最近活跃天数，0=今日")
    hr_active_text: Optional[str] = Field(default=None, description="HR活跃原文，如'HR刚刚在线'")
    is_headhunter: bool = Field(default=False, description="是否猎头")
    is_internship: bool = Field(default=False, description="是否实习岗")
    job_desc: Optional[str] = Field(default=None, description="职位描述（有需要时才获取详情）")
    is_applied: bool = Field(default=False, description="是否已投递过（根据本地记录判断）")
    match_reason: Optional[str] = Field(default=None, description="匹配/跳过原因，用于提示用户")
    need_jd_check: Optional[bool] = Field(default=False, description="标题通用，需读JD确认AI内容")
    jd_ai_verified: Optional[bool] = Field(default=False, description="JD含AI关键词，校验通过")


class JobSearchRequest(BaseModel):
    """职位搜索请求参数"""
    session_id: int = Field(description="平台登录会话ID")
    task_id: Optional[int] = Field(default=None, description="可选，基于任务配置搜索")
    keywords: Union[str, List[str]] = Field(description="搜索关键词，支持多个（列表或逗号分隔）")
    jd_ai_check: bool = Field(default=True, description="JD级AI校验：仅保留AI应用开发岗。投普通开发/测试岗时应关闭")
    headless: Optional[bool] = Field(default=None, description="是否无头运行，空则用全局配置PLAYWRIGHT_HEADLESS")
    city_code: Optional[Union[str, List[str]]] = Field(default=None, description="城市编码，支持多个（多城市会逐个搜索后合并），空=全国")
    salary_min: Optional[int] = Field(default=None)
    salary_max: Optional[int] = Field(default=None)
    experience: Optional[Union[int, List[int]]] = Field(default=None, description="经验要求，支持多个，空=不限")
    education: Optional[Union[int, List[int]]] = Field(default=None, description="学历要求，支持多个，空=不限")
    company_scales: Optional[Union[str, int, List[int]]] = Field(default=None, description="公司规模，支持多个：1=0-20人 2=20-99人 3=100-499人 4=500-999人 5=1000-9999人 6=10000人以上")
    rest_policy: Optional[Union[str, List[str]]] = Field(default=None, description="休息制度，支持多个：双休/大小周/单休，空=不限")
    page: int = Field(default=1, description="抓取第几页")
    page_size: int = Field(default=30, description="抓取数量")


class ApplyJobsRequest(BaseModel):
    """批量投递请求"""
    session_id: int = Field(description="平台登录会话ID")
    task_id: Optional[int] = Field(default=None, description="任务ID")
    resume_id: Optional[int] = Field(default=None, description="简历ID")
    headless: Optional[bool] = Field(default=None, description="是否无头运行，空则用全局配置PLAYWRIGHT_HEADLESS")
    jobs: List[JobItem] = Field(description="待投递的职位列表")
    apply_mode: str = Field(default="semi", description="投递模式")
    greeting_template: Optional[str] = Field(default=None, description="打招呼模板")
    daily_limit: Optional[int] = Field(default=None, description="本次投递打招呼名额上限，空则用全局配置BOSS_DAILY_LIMIT（用完为止）")
    title_filter: Optional[str] = Field(default=None, description="投递前标题方向终检：strict=AI开发岗严格/loose=宽松/None=不校验")
    rest_policy: Optional[List[str]] = Field(default=None, description="休息制度终检：双休/大小周/单休，空=不检查")


class FollowUpRunRequest(BaseModel):
    """自动跟进扫描请求"""
    session_id: Optional[int] = Field(default=None, description="Boss平台会话ID，空=自动选择已登录会话")
    headless: Optional[bool] = Field(default=None, description="是否无头运行，空=有头（保留窗口处理滑块验证）")
    force: bool = Field(default=False, description="是否强制扫描：True=忽略风控冷却，立即重新检测（用户主动点击时用）")
