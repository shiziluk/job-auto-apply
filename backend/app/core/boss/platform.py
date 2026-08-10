"""
Boss直聘平台适配器 - 组合三个Mixin
"""
from app.core.base import (
    BasePlatform,
    BrowserContextManager,
    Job,
    ApplyResult,
)
from app.core.boss.auth import BossAuthMixin
from app.core.boss.scraper import BossScraperMixin
from app.core.boss.applier import BossApplierMixin
from app.core.boss.followup import BossFollowUpMixin


class BossPlatform(BossAuthMixin, BossScraperMixin, BossApplierMixin, BossFollowUpMixin, BasePlatform):
    """
    Boss直聘平台完整适配器
    继承登录认证、职位抓取、自动投递、自动跟进四部分能力
    """

    def __init__(self, browser: BrowserContextManager):
        super().__init__(browser)
        # 确保Mixin初始化顺序没问题
        BasePlatform.__init__(self, browser)

    async def quick_check(self) -> dict:
        """快速自检：当前登录状态 + 账号信息"""
        logged_in = await self.is_logged_in()
        account = {}
        if logged_in:
            try:
                account = await self.get_account_info()
            except Exception:
                pass
        return {
            "platform": self.platform,
            "platform_name": self.platform_name,
            "is_logged_in": logged_in,
            "account": account,
        }


# ============ 平台工厂 ============
PLATFORMS = {
    "boss": BossPlatform,
}


def create_platform(platform: str, browser: BrowserContextManager) -> BasePlatform:
    """平台工厂函数"""
    if platform not in PLATFORMS:
        raise ValueError(
            f"不支持的平台: {platform}, 可用平台: {list(PLATFORMS.keys())}"
        )
    return PLATFORMS[platform](browser)


__all__ = [
    "BossPlatform",
    "PLATFORMS",
    "create_platform",
    "BrowserContextManager",
    "Job",
    "ApplyResult",
]
