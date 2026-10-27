"""Shared browser automation primitives."""

from app.core.base import (
    ApplyResult,
    BasePlatform,
    BrowserContextManager,
    Job,
    async_random_sleep,
    random_sleep,
)
from app.core.boss.platform import BossPlatform, create_platform

__all__ = [
    "ApplyResult",
    "BasePlatform",
    "BossPlatform",
    "BrowserContextManager",
    "Job",
    "async_random_sleep",
    "create_platform",
    "random_sleep",
]
