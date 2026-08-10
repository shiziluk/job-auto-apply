"""
招聘平台适配器 - 基类设计
参考 JobClaw 的 scraper/base.py + applier/base.py 架构
所有平台（Boss直聘/拉勾/前程无忧等）都需要实现以下抽象接口
"""
import os
import json
import time
import random
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field, asdict

from app.config import settings


# ============ 数据对象（领域模型） ============
@dataclass
class Job:
    """统一的职位对象（所有平台抓取后都转成这个格式）"""
    platform: str                    # 平台标识
    job_id: str                      # 平台内部职位ID
    job_title: str = ""              # 职位名称
    job_url: str = ""                # 详情页URL
    company_id: Optional[str] = None # 公司ID
    company_name: str = ""           # 公司名称
    company_size: str = ""           # 公司规模文本
    company_industry: str = ""       # 行业
    salary_min: Optional[int] = None # 最低薪资K
    salary_max: Optional[int] = None # 最高薪资K
    salary_months: Optional[int] = None # 14薪等
    salary_text: str = ""            # 薪资原文
    city: str = ""                   # 城市
    area: str = ""                   # 区域
    experience: str = ""             # 经验要求文本
    education: str = ""              # 学历要求文本
    tags: List[str] = field(default_factory=list) # 职位标签
    rest_policy: str = ""                   # 休息制度：双休/大小周/单休（空=未知）
    job_desc: str = ""               # 职位描述（抓取详情后才有）

    # HR信息
    hr_name: str = ""
    hr_title: str = ""
    hr_active_days: Optional[int] = None  # 0=今日, 空=未知
    hr_active_text: str = ""              # 原文，如"HR刚刚在线"

    # 标记
    is_headhunter: bool = False     # 是否猎头岗位
    is_internship: bool = False     # 是否实习
    is_applied: bool = False        # 本地是否已投递过
    match_reason: str = ""          # 匹配/跳过原因说明
    need_jd_check: bool = False     # 标题通用（无AI词），需读JD确认是否AI应用开发岗
    jd_ai_verified: bool = False    # JD校验通过（JD含AI关键词）

    def to_dict(self):
        return asdict(self)


@dataclass
class ApplyResult:
    """投递结果"""
    job_id: str
    success: bool
    status: str = "pending"  # success/failed/skipped/duplicate
    message: str = ""
    greeting_sent: str = ""
    applied_at: Optional[float] = None

    def to_dict(self):
        return asdict(self)


# ============ 浏览器上下文管理 ============
class BrowserContextManager:
    """Playwright 浏览器 + 上下文管理器
    负责：启动浏览器、加载Cookie、保存Cookie、反检测设置
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        slow_mo: Optional[int] = None,
        user_data_dir: Optional[str] = None,
        browser_type: Optional[str] = None,
    ):
        self.browser_type = (browser_type or settings.PLAYWRIGHT_BROWSER or "firefox").lower()
        self.headless = headless if headless is not None else settings.PLAYWRIGHT_HEADLESS
        self.slow_mo = slow_mo if slow_mo is not None else settings.PLAYWRIGHT_SLOW_MO
        self.user_data_dir = user_data_dir  # 持久化用户数据目录（可选）
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self):
        """启动浏览器 - 使用持久化上下文规避反爬检测
        默认Firefox：Boss直聘对Playwright Chromium检测严格（会被风控弹回/关闭），
        Firefox无明显自动化指纹，稳定性好；可用PLAYWRIGHT_BROWSER=chromium切换
        """
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()

        is_ff = self.browser_type == "firefox"
        browser_type_obj = self._playwright.firefox if is_ff else self._playwright.chromium

        # 反检测launch参数（Chromium专属）
        launch_args = []
        if not is_ff:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--window-size=1440,900",
            ]
        # 优先使用系统Chrome（仅Chromium时可用，反检测效果最好）
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        use_chrome_channel = (not is_ff) and os.path.exists(chrome_path)

        # 每个浏览器类型独立的用户数据目录（避免profile冲突）
        browser_data_dir = os.path.join(
            settings.DATA_DIR or os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ".browser_data",
            self.browser_type,
        )
        os.makedirs(browser_data_dir, exist_ok=True)

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"
            if is_ff else
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        context_kwargs = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": user_agent,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "color_scheme": "light",
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "java_script_enabled": True,
            "ignore_https_errors": True,
        }

        if self.user_data_dir and isinstance(self.user_data_dir, dict):
            # storage_state 字典（数据库中的Cookie）只能用于 new_context：
            # launch_persistent_context 不支持 storage_state 参数，硬传会报错回退导致每次全新profile、易触发风控
            self._browser = await browser_type_obj.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=launch_args or None,
                channel="chrome" if use_chrome_channel else None,
            )
            self._context = await self._browser.new_context(storage_state=self.user_data_dir, **context_kwargs)
        else:
            # 持久化上下文（反检测效果最好）：复用 .browser_data/{browser_type} 用户数据目录，
            # 登录态/localStorage/指纹保持一致，规避Boss风控。
            # 注意：不要在这里静默回退到普通模式（非持久化）——那会导致登录态全部丢失、
            # 每次打开都像“未登录”，而且可能多弹出一个窗口。启动失败就重试，重试仍失败则明确报错。
            # 启动前清理上次异常退出残留的 Firefox profile 锁文件，避免被误判为“profile 被占用”而挂起。
            def _clean_stale_lock():
                if not is_ff or not os.path.isdir(browser_data_dir):
                    return
                for name in ("parent.lock", ".parentlock", "lock"):
                    lock_path = os.path.join(browser_data_dir, name)
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except OSError:
                        pass

            last_err = None
            for attempt in range(1, 4):
                _clean_stale_lock()
                try:
                    self._context = await browser_type_obj.launch_persistent_context(
                        user_data_dir=browser_data_dir,
                        headless=self.headless,
                        slow_mo=self.slow_mo,
                        args=launch_args or None,
                        channel="chrome" if use_chrome_channel else None,
                        timeout=60000,  # 快速失败：避免单次尝试卡默认 180 秒，3 次重试最多 3 分钟
                        **context_kwargs,
                    )
                    # persistent context 的 browser 属性
                    self._browser = self._context.browser
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print(f"[WARN] 持久化浏览器启动失败(第{attempt}次): {e}")
                    if attempt < 3:
                        await asyncio.sleep(2 + attempt)
            if last_err is not None:
                # 明确报错而不是回退到无登录态的全新浏览器
                raise RuntimeError(
                    "持久化浏览器启动失败：profile 可能被上一个浏览器实例占用（例如登录/搜索窗口还在运行），"
                    "请等待几秒后重试。如果持续失败，请重启应用。原因: %s" % last_err
                )

        # 注入反检测脚本（Firefox/Chromium 指纹差异分开处理，避免给 Firefox 注入 Chromium 专属特征）
        init_script = """
            // 覆盖 webdriver 标记
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters);
            // 覆盖 languages / platform / hardwareConcurrency
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        """
        if not is_ff:
            # Chromium 专属指纹：chrome 对象、plugins、deviceMemory（Firefox 本身没有，注入反而像自动化）
            init_script += """
            window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """
        await self._context.add_init_script(init_script)

        # launch_persistent_context 会自动创建一个初始空白页，直接复用它，避免多弹出一个窗口
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        # 设置默认超时
        self._page.set_default_timeout(30000)
        return self._page

    async def save_storage_state(self, path: str):
        """保存浏览器存储状态（Cookie + LocalStorage + SessionStorage）"""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        state = await self._context.storage_state()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return state

    async def load_storage_state(self, state: Dict):
        """从字典加载存储状态"""
        # 关掉当前context，用storage_state重建
        if self._context:
            await self._context.close()
        self._context = await self._browser.new_context(storage_state=state)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(30000)
        return self._page

    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    async def close(self):
        """关闭浏览器"""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


# ============ 工具方法 ============
def random_sleep(min_sec: float, max_sec: Optional[float] = None):
    """随机等待（模拟人类操作节奏）"""
    if max_sec is None:
        max_sec = min_sec
        min_sec = max_sec * 0.7
    t = random.uniform(min_sec, max_sec)
    time.sleep(t)
    return t


async def async_random_sleep(min_sec: float, max_sec: Optional[float] = None):
    if max_sec is None:
        max_sec = min_sec
        min_sec = max_sec * 0.7
    t = random.uniform(min_sec, max_sec)
    await asyncio.sleep(t)
    return t


# ============ 平台基类 ============
class BasePlatform(ABC):
    """所有招聘平台的抽象基类"""
    platform: str = ""
    platform_name: str = ""
    base_url: str = ""

    def __init__(self, browser: BrowserContextManager):
        self.browser = browser
        self.page = browser.page
        self._cookies = None
        # 投递频率控制
        self.delay_min = settings.BOSS_APPLY_DELAY_MIN
        self.delay_max = settings.BOSS_APPLY_DELAY_MAX
        # 打招呼后在聊天页停留时长（防封：调久以降低被风控判定的概率）
        self.post_greeting_dwell_min = settings.BOSS_POST_GREETING_DWELL_MIN
        self.post_greeting_dwell_max = settings.BOSS_POST_GREETING_DWELL_MAX
        # 打开职位详情页后模拟浏览时长（防封：读JD再点沟通）
        self.page_view_min = settings.BOSS_PAGE_VIEW_MIN
        self.page_view_max = settings.BOSS_PAGE_VIEW_MAX
        self.daily_limit = settings.BOSS_DAILY_LIMIT
        self.skip_inactive_days = settings.BOSS_SKIP_INACTIVE_DAYS
        # 回调钩子
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_status_change: Optional[Callable[[str, Any], None]] = None

    def log(self, msg: str):
        if self.on_log:
            self.on_log(f"[{self.platform_name}] {msg}")

    # ---------- 登录认证 ----------
    @abstractmethod
    async def goto_login_page(self) -> bool:
        """跳转到登录页面"""
        ...

    @abstractmethod
    async def is_logged_in(self) -> bool:
        """检测当前是否已经登录"""
        ...

    @abstractmethod
    async def get_account_info(self) -> Dict:
        """获取当前登录账号信息（昵称、头像等）"""
        ...

    # ---------- 职位搜索抓取 ----------
    @abstractmethod
    async def search_jobs(
        self,
        keywords: str,
        city_code: Optional[str] = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        experience: int = 0,
        education: int = 0,
        page: int = 1,
        page_size: int = 30,
        **kwargs
    ) -> List[Job]:
        """搜索职位列表，返回统一格式的Job列表"""
        ...

    @abstractmethod
    async def get_job_detail(self, job: Job) -> Job:
        """获取职位详情（含完整JD）"""
        ...

    # ---------- 投递 ----------
    @abstractmethod
    async def apply_job(
        self,
        job: Job,
        greeting_template: Optional[str] = None,
        resume_id: Optional[str] = None,
    ) -> ApplyResult:
        """投递单个职位"""
        ...

    async def apply_batch(
        self,
        jobs: List[Job],
        greeting_template: Optional[str] = None,
        resume_id: Optional[str] = None,
        stop_event: Optional[asyncio.Event] = None,
        on_progress: Optional[Callable[[int, int, Job, ApplyResult], None]] = None,
    ) -> List[ApplyResult]:
        """批量投递（带频率控制 + 进度回调）"""
        results = []
        total = len(jobs)
        for idx, job in enumerate(jobs, 1):
            if stop_event and stop_event.is_set():
                self.log("收到停止信号，终止投递")
                break
            self.log(f"投递进度: {idx}/{total} - {job.company_name} {job.job_title}")
            try:
                result = await self.apply_job(job, greeting_template, resume_id)
                results.append(result)
            except Exception as e:
                self.log(f"投递异常: {e}")
                results.append(ApplyResult(
                    job_id=job.job_id, success=False,
                    status="failed", message=str(e)
                ))
            # 进度回调
            if on_progress:
                on_progress(idx, total, job, results[-1])
            # 随机等待
            if idx < total and not (stop_event and stop_event.is_set()):
                waited = await async_random_sleep(self.delay_min, self.delay_max)
                self.log(f"等待 {waited:.1f} 秒...")
        return results
