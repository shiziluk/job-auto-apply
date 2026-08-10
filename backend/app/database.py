"""
数据库连接与ORM基础配置
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

from app.config import settings

# 确保数据库相关目录存在
os.makedirs(os.path.dirname(settings.SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")), exist_ok=True) \
    if settings.SQLALCHEMY_DATABASE_URL.startswith("sqlite") else None

# 创建数据库引擎
engine_kwargs = {
    "echo": settings.APP_DEBUG,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if settings.SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # SQLite特殊配置：多线程支持 + 静态连接池
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URL,
    **engine_kwargs
)

# 数据库会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM模型基类
Base = declarative_base()


def get_db():
    """FastAPI依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_db_schema():
    """轻量级schema升级：为已存在的表补充新列（create_all不会修改已存在的表）"""
    try:
        from sqlalchemy import inspect, text
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "apply_tasks" in tables:
            cols = {c["name"] for c in insp.get_columns("apply_tasks")}
            if "progress" not in cols:
                col_type = "TEXT" if engine.dialect.name == "sqlite" else "JSON"
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE apply_tasks ADD COLUMN progress {col_type}"))
                print("✅ 已为 apply_tasks 表补充 progress 列")
            if "rest_policy" not in cols:
                col_type = "JSON" if engine.dialect.name != "sqlite" else "TEXT"
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE apply_tasks ADD COLUMN rest_policy {col_type}"))
                print("✅ 已为 apply_tasks 表补充 rest_policy 列")
    except Exception as e:
        print(f"[WARN] 数据库schema升级失败（新库会自动建表，可忽略）: {e}")
