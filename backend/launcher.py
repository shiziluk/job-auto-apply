"""
牛人Agent - 桌面版启动器（PyInstaller 打包入口）
功能：设置数据目录/浏览器路径 -> 启动后端服务 -> 自动打开默认浏览器
"""
import os
import sys
import threading
import webbrowser


def _fix_std_streams():
    # PyInstaller 窗口模式（console=False）下 sys.stdout/sys.stderr 为 None，
    # uvicorn 等库会调用 .isatty() 导致崩溃，这里替换成 devnull 文件对象。
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

def _setup_paths():
    # 数据目录：SQLite / 浏览器登录态 / 上传 / cookies（放 %APPDATA% 避免安装目录不可写）
    data_dir = os.environ.get("DATA_DIR") or os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), "牛人Agent"
    )
    os.environ["DATA_DIR"] = data_dir
    os.makedirs(data_dir, exist_ok=True)
    # 打包目录下的前端静态资源与 Playwright 浏览器
    base_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    # PyInstaller 6 onedir 模式会把数据文件放进 _internal/，两个位置都探测
    _candidates = [
        os.path.join(base_dir, "web", "dist"),
        os.path.join(base_dir, "_internal", "web", "dist"),
    ]
    for _d in _candidates:
        if os.path.isdir(_d):
            os.environ["FRONTEND_DIST"] = _d
            break
    _pw_candidates = [
        os.path.join(base_dir, "ms-playwright"),
        os.path.join(base_dir, "_internal", "ms-playwright"),
    ]
    for _d in _pw_candidates:
        if os.path.isdir(_d):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _d
            break


def main():
    _fix_std_streams()
    _setup_paths()
    # 延迟打开浏览器，等服务就绪
    threading.Timer(3.0, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    import uvicorn
    from main import app  # noqa: F401  (PyInstaller 静态收集依赖)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
