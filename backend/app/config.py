"""
应用配置管理
参考 JobClaw 的设计，使用 pydantic-settings 统一管理配置
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置类"""
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # ===== 应用配置 =====
    APP_NAME: str = "牛人Agent"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "jobagent-secret-key-2026-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24 * 30  # 30天有效期

    # ===== 数据库配置 =====
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_NAME: Optional[str] = None
    # 也可以直接提供DB_URL，优先级最高
    DB_URL: Optional[str] = None

    # ===== 上传配置 =====
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    # 数据根目录（安装版通过环境变量 DATA_DIR 指向 %APPDATA%\牛人Agent；开发默认当前工作目录 backend/）
    DATA_DIR: Optional[str] = None

    # ===== Playwright 配置 =====
    PLAYWRIGHT_HEADLESS: bool = True  # 搜索/投递默认无头运行；登录扫码固定有头，调试可在.env设为false
    PLAYWRIGHT_SLOW_MO: int = 100  # 操作延迟毫秒，模拟人类
    PLAYWRIGHT_BROWSER: str = "firefox"  # 浏览器类型：firefox/chromium；Boss对Chromium风控严格（页面会变空白），默认Firefox

    # ===== Boss直聘防封配置（保守策略） =====
    # 2026-08-09：账号曾因高频投递被风控临时限制（403 code=32），用户要求把打招呼后的停留时间调久。
    BOSS_APPLY_DELAY_MIN: float = 4.5  # 职位间随机延迟下限（防封重新调大：2.5→3.0）
    BOSS_APPLY_DELAY_MAX: float = 7.5  # 职位间随机延迟上限（防封重新调大：4.0→5.5）
    BOSS_POST_GREETING_DWELL_MIN: float = 6.0  # 打招呼后在聊天页停留下限（原0.3s，防封调久）
    BOSS_POST_GREETING_DWELL_MAX: float = 9.0  # 打招呼后在聊天页停留上限（原0.5s，防封调久）
    BOSS_PAGE_VIEW_MIN: float = 5.0  # 打开职位详情页后模拟浏览时长下限（读JD再点沟通，防机器特征）
    BOSS_PAGE_VIEW_MAX: float = 10.0  # 模拟浏览时长上限
    BOSS_DAILY_LIMIT: int = 150  # Boss每日打招呼名额上限（用户实测为150，非120）
    BOSS_SKIP_INACTIVE_DAYS: int = 7

    # ===== QQ 通知/命令通道（官方机器人，需在QQ开放平台申请并通过审核） =====
    QQ_BOT_ENABLED: bool = False  # 开启后投递结果会推送到 QQ
    QQ_BOT_APP_ID: str = ""       # QQ开放平台机器人 AppID
    QQ_BOT_APP_SECRET: str = ""   # QQ开放平台机器人 AppSecret（用于换取 access_token）
    QQ_BOT_TARGET_UID: str = ""   # 接收消息的QQ用户 openid（bot 需要先与该用户建立会话）


    @property
    def UPLOAD_DIR(self) -> str:
        return os.path.join(self.DATA_DIR or ".", "uploads")

    @property
    def COOKIE_SAVE_DIR(self) -> str:
        return os.path.join(self.DATA_DIR or ".", "cookies")

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """生成SQLAlchemy数据库连接URL"""
        if self.DB_URL:
            return self.DB_URL
        if self.DB_HOST and self.DB_USER and self.DB_NAME:
            # MySQL连接
            pwd = self.DB_PASSWORD or ""
            return f"mysql+pymysql://{self.DB_USER}:{pwd}@{self.DB_HOST}:{self.DB_PORT or 3306}/{self.DB_NAME}?charset=utf8mb4"
        # 默认SQLite，方便快速调试（数据目录 DATA_DIR 或当前目录）
        data_dir = self.DATA_DIR or "."
        return f"sqlite:///{os.path.join(data_dir, 'job_auto.db')}"


# 全局单例配置
settings = Settings()
