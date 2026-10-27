"""Pydantic request and response schemas."""

from app.schemas.apply import (
    ApplyJobsRequest,
    ApplyRecordBase,
    ApplyRecordInfo,
    ApplyTaskBase,
    ApplyTaskCreate,
    ApplyTaskInfo,
    ApplyTaskUpdate,
    FollowUpRunRequest,
    JobItem,
    JobSearchRequest,
)
from app.schemas.common import PageParams, PageResult, ResponseModel
from app.schemas.filter_rule import (
    FilterRuleBase,
    FilterRuleCreate,
    FilterRuleInfo,
    FilterRuleUpdate,
)
from app.schemas.platform_session import (
    LoginStartRequest,
    LoginStatusResponse,
    PlatformSessionBase,
    PlatformSessionCreate,
    PlatformSessionInfo,
    PlatformSessionUpdate,
)
from app.schemas.resume import (
    ResumeBase,
    ResumeCreate,
    ResumeInfo,
    ResumeUpdate,
    ResumeUploadResponse,
)

__all__ = [
    "ApplyJobsRequest",
    "ApplyRecordBase",
    "ApplyRecordInfo",
    "ApplyTaskBase",
    "ApplyTaskCreate",
    "ApplyTaskInfo",
    "ApplyTaskUpdate",
    "FilterRuleBase",
    "FilterRuleCreate",
    "FilterRuleInfo",
    "FilterRuleUpdate",
    "FollowUpRunRequest",
    "JobItem",
    "JobSearchRequest",
    "LoginStartRequest",
    "LoginStatusResponse",
    "PageParams",
    "PageResult",
    "PlatformSessionBase",
    "PlatformSessionCreate",
    "PlatformSessionInfo",
    "PlatformSessionUpdate",
    "ResponseModel",
    "ResumeBase",
    "ResumeCreate",
    "ResumeInfo",
    "ResumeUpdate",
    "ResumeUploadResponse",
]
