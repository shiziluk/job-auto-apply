"""
FastAPI 应用入口
"""
import os
import sys
import asyncio

# Windows下必须使用ProactorEventLoop，否则Playwright无法启动子进程
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 确保backend目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows下控制台/日志重定向默认可能是GBK，统一为UTF-8，避免打印emoji/中文时崩溃
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine



# ============ 后台自动跟进周期任务 ============
FOLLOWUP_INTERVAL = 7200  # 每2小时扫描一次（用户出门时自动跟进）
FOLLOWUP_FIRST_DELAY = 60  # 启动后1分钟开始首次扫描


async def _followup_loop():
    """后台周期任务：Boss聊天页自动跟进扫描（仅当无投递任务运行时执行）"""
    from app.api.apply import RUNNING_APPLY_TASKS
    from app.database import SessionLocal
    from app.models import ApplyTask, PlatformSession
    from app.services.followup_service import run_followup_scan_sync

    await asyncio.sleep(FOLLOWUP_FIRST_DELAY)
    while True:
        try:
            # 浏览器profile独占：有投递任务运行时跳过，避免两个Firefox实例争用同一profile
            busy = bool(RUNNING_APPLY_TASKS)
            if not busy:
                db = SessionLocal()
                try:
                    busy = db.query(ApplyTask).filter(ApplyTask.status == "running").first() is not None
                finally:
                    db.close()
            if busy:
                print("[跟进] 有投递任务运行中，本次自动跟进跳过")
                await asyncio.sleep(FOLLOWUP_INTERVAL)
                continue
            # 没有登录会话也跳过
            db = SessionLocal()
            try:
                has_session = db.query(PlatformSession).filter(
                    PlatformSession.user_id == 1,
                    PlatformSession.platform == "boss",
                    PlatformSession.is_logged_in == True,  # noqa: E712
                ).first() is not None
            finally:
                db.close()
            if not has_session:
                print("[跟进] 无已登录Boss会话，自动跟进跳过")
                await asyncio.sleep(FOLLOWUP_INTERVAL)
                continue
            # 有头模式运行：若弹滑块/需扫码，窗口保留等待用户处理
            result = await asyncio.to_thread(run_followup_scan_sync, 1, None, False)
            print(f"[跟进] 自动扫描完成: {result}")
        except Exception as e:
            print(f"[跟进] 自动扫描失败: {e}")
        await asyncio.sleep(FOLLOWUP_INTERVAL)

# ============ 生命周期事件 ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的事件"""
    # 启动：初始化数据库表
    print(f"🚀 {settings.APP_NAME} 启动中...")
    print(f"📦 数据库连接: {settings.SQLALCHEMY_DATABASE_URL}")

    # 导入所有模型，确保Base.metadata能识别到所有表
    from app import models  # noqa: F401
    # 创建所有表（如果不存在）
    Base.metadata.create_all(bind=engine)
    # 增量升级已有表的schema（如补充新列）
    from app.database import ensure_db_schema
    ensure_db_schema()
    print("✅ 数据库表初始化完成")

    # 确保必要目录存在
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.COOKIE_SAVE_DIR, exist_ok=True)
    print("✅ 目录初始化完成")

    # 启动后台自动跟进周期任务（用户出门时自动扫描Boss聊天页更新跟进状态）
    followup_task = asyncio.create_task(_followup_loop())
    print("✅ 自动跟进周期任务已启动（每2小时扫描一次）")

    yield

    # 关闭：清理资源
    followup_task.cancel()
    try:
        await followup_task
    except asyncio.CancelledError:
        pass
    print(f"👋 {settings.APP_NAME} 已关闭")


# ============ 创建 FastAPI 应用 ============
app = FastAPI(
    title=settings.APP_NAME,
    description="牛人Agent - 智能求职投递系统（JobClaw）| 求职者视角的自动化投递助手 · 对标HR Agent",
    version="0.1.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
)

# ============ CORS 跨域配置（开发阶段前后端分离用）============
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ============ 静态文件：上传目录 ============
if not os.path.exists(settings.UPLOAD_DIR):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# ============ 基础路由 ============
@app.get("/", tags=["系统"])
async def root():
    """根路径：前端构建产物存在时直接返回前端页面，否则返回系统信息（API探测用）"""
    _front = os.environ.get("FRONTEND_DIST") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
    _idx = os.path.join(_front, "index.html")
    if os.path.isfile(_idx):
        from fastapi.responses import FileResponse
        return FileResponse(_idx)
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口"""
    # 简单检查数据库连接
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "database": db_status,
        "env": settings.APP_ENV,
    }


# ============ 挂载各模块API路由 ============
from app.api.platform import router as platform_router
from app.api.resume import router as resume_router
from app.api.apply import router as apply_router
from app.api.filter import router as filter_router
from app.api.auth import router as auth_router

app.include_router(auth_router, prefix="/api")
app.include_router(platform_router, prefix="/api")
app.include_router(resume_router, prefix="/api")
app.include_router(apply_router, prefix="/api")
app.include_router(filter_router, prefix="/api")

# ============ 生产模式：托管前端构建产物（frontend/dist，hash路由无需SPA fallback）============
_frontend_dist = os.environ.get(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"),
)
if os.path.isdir(_frontend_dist):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
    print(f"✅ 前端静态资源已挂载: {_frontend_dist}")


# ============ API路由总览（调试用）============
@app.get("/api/routes", tags=["系统"], include_in_schema=False)
async def list_all_routes():
    """快速查看所有已注册的API路由"""
    routes = []
    for r in app.routes:
        try:
            path = getattr(r, "path", "")
            methods = sorted(getattr(r, "methods", []) or [])
            name = getattr(r, "name", "")
            if path.startswith("/api") and methods:
                routes.append({"methods": methods, "path": path, "name": name})
        except Exception:
            pass
    return {"total": len(routes), "routes": sorted(routes, key=lambda x: x["path"])}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
    )
