"""
平台登录 & 会话管理 API
核心流程：
1. POST /api/platform/login/start       -> 启动后台任务：打开Playwright浏览器扫码页
2. GET  /api/platform/login/status/{id}  -> 轮询登录状态（waiting/logged_in/failed/timeout）
3. GET  /api/platform/sessions           -> 会话列表
4. POST /api/platform/session/{id}/check -> 检查Cookie是否还有效
5. POST /api/platform/session/{id}/logout -> 登出/删除会话

MVP版本关键：采用asyncio.create_task后台启动浏览器，用全局dict存任务状态
"""
import os
import json
import time
import asyncio
import datetime
from typing import Dict, Optional, List
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, Base, engine
from app.config import settings
from app.models import User, PlatformSession
from app.schemas import (
    PlatformSessionCreate, PlatformSessionUpdate, PlatformSessionInfo,
    LoginStartRequest, LoginStatusResponse, ResponseModel,
)
from app.api.deps import get_current_user

# ============ 后台登录任务管理 ============
# 全局任务状态存储（生产环境建议用Redis，MVP用内存dict即可）
LOGIN_TASKS: Dict[str, Dict] = {}
# 活跃的Browser实例引用（方便随时关闭）
ACTIVE_BROWSERS: Dict[str, object] = {}

router = APIRouter(tags=["平台登录"])


def _clean_old_tasks():
    """清理超过10分钟的老任务"""
    now = time.time()
    for tid in list(LOGIN_TASKS.keys()):
        if now - LOGIN_TASKS[tid].get("created_at", 0) > 600:
            with suppress(Exception):
                LOGIN_TASKS.pop(tid, None)
                ACTIVE_BROWSERS.pop(tid, None)


# ========== 启动扫码登录 ==========
@router.post("/platform/login/start", response_model=ResponseModel[LoginStatusResponse])
async def start_platform_login(
    req: LoginStartRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """启动Boss直聘扫码登录（弹出Playwright浏览器）"""
    from app.core import BrowserContextManager, create_platform

    _clean_old_tasks()

    if req.platform != "boss":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"暂不支持平台: {req.platform}，目前仅支持boss")

    task_id = f"login_{int(time.time())}_{os.urandom(4).hex()}"
    LOGIN_TASKS[task_id] = {
        "task_id": task_id,
        "user_id": user.id,
        "platform": req.platform,
        "status": "waiting",   # waiting / logged_in / failed / timeout / canceling
        "message": "浏览器启动中，请在弹出的浏览器中扫码登录",
        "session_id": None,
        "created_at": time.time(),
    }

    # 启动后台异步任务
    asyncio.create_task(_run_login_task(task_id, req.platform, user.id))

    return ResponseModel.success(data=LoginStatusResponse(
        task_id=task_id,
        status="waiting",
        message="已启动浏览器，请在弹出的窗口中完成Boss直聘扫码登录...",
    ), message="登录任务已启动")


async def _run_login_task(task_id: str, platform: str, user_id: int):
    """后台执行登录流程 - 在独立线程+ProactorEventLoop中运行Playwright"""
    # 在独立线程中运行Playwright，避免uvicorn事件循环不支持子进程的问题
    await asyncio.to_thread(_run_login_task_sync, task_id, platform, user_id)


def _run_login_task_sync(task_id: str, platform: str, user_id: int):
    """同步入口：创建独立事件循环运行Playwright登录流程"""
    import asyncio
    import sys
    # Windows下必须使用ProactorEventLoop
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_do_login(task_id, platform, user_id))
    except Exception as e:
        task = LOGIN_TASKS.get(task_id)
        if task:
            task["status"] = "failed"
            task["message"] = f"登录异常: {str(e)[:200]}"
    finally:
        loop.close()


async def _do_login(task_id: str, platform: str, user_id: int):
    """实际的Playwright登录流程"""
    from app.core import BrowserContextManager, create_platform

    task = LOGIN_TASKS.get(task_id)
    if not task:
        return
    browser = None
    try:
        # 1. 启动浏览器（必须显示，不能无头！）
        browser = BrowserContextManager(headless=False, slow_mo=settings.PLAYWRIGHT_SLOW_MO, browser_type="firefox")
        ACTIVE_BROWSERS[task_id] = browser
        await browser.start()
        task["status"] = "waiting"
        task["message"] = "浏览器已打开，请扫码登录"

        # 2. 创建平台适配器并打开登录页
        pf = create_platform(platform, browser)
        pf.on_log = lambda msg: _update_task_msg(task_id, msg[:120])
        await pf.goto_login_page()

        # 2.5 如果profile里已是登录态（goto_login_page已跳过登录页），直接标记登录成功
        if await pf.is_logged_in():
            task = LOGIN_TASKS.get(task_id)
            if task:
                task["message"] = "检测到已处于登录状态，无需扫码"

        # 3. 轮询等待登录完成，最长3分钟
        timeout = 180
        start = time.time()
        verify_hint_shown = False
        while time.time() - start < timeout:
            task = LOGIN_TASKS.get(task_id)
            if not task or task.get("status") == "canceling":
                await browser.close()
                return
            # 检测安全验证页，引导用户手动完成滑块验证（Boss风控：IP异常时弹出code=35安全验证）
            if not verify_hint_shown:
                try:
                    cur = browser.page.url.lower()
                    if "verify" in cur or "passport" in cur:
                        task["message"] = "检测到Boss安全验证（当前IP可能异常）：请在弹出的浏览器窗口中点击『点击按钮进行验证』完成滑块，验证通过后会自动继续"
                        verify_hint_shown = True
                except Exception:
                    pass
            if await pf.is_logged_in():
                break
            await asyncio.sleep(3)

        # 超时检查
        if not await pf.is_logged_in():
            task = LOGIN_TASKS.get(task_id)
            if task:
                task["status"] = "timeout"
                task["message"] = "登录超时，请重试"
            await browser.close()
            return

        # 4. 登录成功 -> 保存Cookie + 入库
        storage_state = await browser.context.storage_state()
        account_info = await pf.get_account_info()

        # 5. 写入数据库
        session_id = await asyncio.to_thread(
            _save_session_to_db, user_id, platform, storage_state, account_info
        )

        # 6. 更新任务状态
        task = LOGIN_TASKS.get(task_id)
        if task:
            task["status"] = "logged_in"
            task["message"] = f"登录成功！账号：{account_info.get('account_name') or '已获取'}"
            task["session_id"] = session_id

    except Exception as e:
        task = LOGIN_TASKS.get(task_id)
        if task:
            task["status"] = "failed"
            task["message"] = f"登录异常: {str(e)[:200]}"
    finally:
        ACTIVE_BROWSERS.pop(task_id, None)
        # 登录成功/异常后都关闭浏览器，避免窗口一直开着占用profile导致下次启动被判未登录
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        await asyncio.sleep(180)
        LOGIN_TASKS.pop(task_id, None)


def _save_session_to_db(user_id: int, platform: str, storage_state: dict, account_info: dict) -> int:
    """保存会话到数据库（同步函数，用to_thread在子线程跑）"""
    from app.database import SessionLocal
    from app.models import PlatformSession

    db = SessionLocal()
    try:
        # 同一用户同一平台先删除老记录
        db.query(PlatformSession).filter(
            PlatformSession.user_id == user_id,
            PlatformSession.platform == platform
        ).delete()

        now = datetime.datetime.now()
        cookies = storage_state.get("cookies", [])
        origins = storage_state.get("origins", [])
        local_storage = None
        session_storage = None
        if origins:
            # LocalStorage
            local_storage = [o for o in origins if o.get("localStorage")] or None
            session_storage = [o for o in origins if o.get("sessionStorage")] or None

        obj = PlatformSession(
            user_id=user_id,
            platform=platform,
            platform_name="Boss直聘" if platform == "boss" else platform,
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
            account_name=account_info.get("account_name", ""),
            account_avatar=account_info.get("account_avatar", ""),
            is_logged_in=True,
            last_check_at=now,
            last_login_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj.id
    finally:
        db.close()


def _update_task_msg(task_id: str, msg: str):
    task = LOGIN_TASKS.get(task_id)
    if task and task.get("status") == "waiting":
        task["message"] = msg


# ========== 查询登录状态 ==========
@router.get("/platform/login/status/{task_id}", response_model=ResponseModel[LoginStatusResponse])
def get_login_status(task_id: str):
    """轮询登录任务状态"""
    task = LOGIN_TASKS.get(task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在或已过期")
    return ResponseModel.success(data=LoginStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        session_id=task.get("session_id"),
        message=task.get("message"),
    ))


# ========== 取消登录 ==========
@router.post("/platform/login/cancel/{task_id}", response_model=ResponseModel)
async def cancel_login(task_id: str):
    task = LOGIN_TASKS.get(task_id)
    if not task:
        return ResponseModel.success(message="任务不存在")
    task["status"] = "canceling"
    # 关闭浏览器
    browser = ACTIVE_BROWSERS.pop(task_id, None)
    if browser:
        with suppress(Exception):
            await browser.close()
    LOGIN_TASKS.pop(task_id, None)
    return ResponseModel.success(message="已取消")


# ========== 会话列表 ==========
@router.get("/platform/sessions", response_model=ResponseModel[List[PlatformSessionInfo]])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    objs = db.query(PlatformSession).filter(PlatformSession.user_id == user.id)\
        .order_by(PlatformSession.updated_at.desc()).all()
    return ResponseModel.success(data=objs)


# ========== 检查Cookie有效性 ==========
@router.post("/platform/session/{session_id}/check", response_model=ResponseModel)
async def check_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """使用Playwright加载Cookie，访问Boss直聘判断是否还登录着"""
    from app.core import BrowserContextManager, create_platform

    obj = db.query(PlatformSession).filter(
        PlatformSession.id == session_id, PlatformSession.user_id == user.id
    ).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    # 重建storage_state
    storage_state = {"cookies": obj.cookies or [], "origins": []}
    if obj.local_storage:
        storage_state["origins"].extend(obj.local_storage)
    if obj.session_storage:
        storage_state["origins"].extend(obj.session_storage)

    browser = None
    try:
        # 用无头模式快速检测
        browser = BrowserContextManager(headless=True)
        await browser.start()
        # 2026-08-10 修复：持久化 profile 已自带最新 cookie（用户扫码写入），
        # 再用数据库旧 cookies 覆盖会把新登录态覆盖成旧/匿名态，导致误判失效。
        # 数据库 cookies 仅用于重建全新 profile 场景（当前固定持久化，无需重建）。
        # await browser.context.add_cookies(obj.cookies or [])        # 访问需要登录的页面
        page = browser.page
        await page.goto("https://www.zhipin.com/web/geek/job-recommend", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        pf = create_platform(obj.platform, browser)
        logged_in = await pf.is_logged_in()

        obj.is_logged_in = logged_in
        obj.last_check_at = datetime.datetime.now()
        if logged_in:
            try:
                acc = await pf.get_account_info()
                if acc.get("account_name"):
                    obj.account_name = acc["account_name"]
                    obj.account_avatar = acc.get("account_avatar", "")
            except Exception:
                pass
        db.commit()

        return ResponseModel.success(
            data={"is_logged_in": logged_in, "account_name": obj.account_name},
            message="Cookie有效" if logged_in else "Cookie已失效，请重新登录"
        )
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"检查失败: {e}")
    finally:
        if browser:
            await browser.close()


# ========== 登出/删除会话 ==========
@router.post("/platform/session/{session_id}/logout", response_model=ResponseModel)
def logout_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    obj = db.query(PlatformSession).filter(
        PlatformSession.id == session_id, PlatformSession.user_id == user.id
    ).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
    db.delete(obj)
    db.commit()
    return ResponseModel.success(message="已登出并删除该会话")
