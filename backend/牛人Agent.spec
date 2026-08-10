# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files('playwright')

def _collect_tree(src_dir, dest_prefix):
    """把目录整体收集进打包产物（保留相对结构）"""
    if not os.path.isdir(src_dir):
        return
    for root, _dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dest = dest_prefix if rel == "." else os.path.join(dest_prefix, rel)
        for f in files:
            datas.append((os.path.join(root, f), dest))

# 前端构建产物 -> 安装目录 web/dist（launcher 会设置 FRONTEND_DIST）
_collect_tree(r"D:\workspace\自动投简历工具\frontend\dist", os.path.join("web", "dist"))
# Playwright 浏览器（仅 Firefox + ffmpeg，应用默认 firefox）-> 安装目录 ms-playwright
_local_pw = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
for _sub in ("firefox-1463", "ffmpeg-1010", ".links"):
    _collect_tree(os.path.join(_local_pw, _sub), os.path.join("ms-playwright", _sub))


a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=['playwright.sync_api', 'playwright.async_api', 'bcrypt'] + collect_submodules('passlib'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 环境里装了但应用不用的重型ML/数据科学库，排除以大幅缩小体积
        'torch', 'torchvision', 'torchaudio', 'spacy', 'cv2', 'pyarrow', 'scipy',
        'transformers', 'faiss', 'langchain', 'langchain_core', 'langchain_community',
        'langchain_google_genai', 'langchain_classic', 'openai', 'openai_agents',
        'litellm', 'nltk', 'gensim', 'sklearn', 'scikit_learn', 'timm', 'onnx',
        'onnxruntime', 'ollama', 'llvmlite', 'numba', 'matplotlib', 'plotly',
        'statsmodels', 'IPython', 'jieba', 'selenium', 'flask', 'kaleido', 'altair',
        'black', 'mypy', 'coverage', 'datasets', 'pymupdf', 'pikepdf', 'pdfminer',
        'redis', 'psycopg', 'psycopg2', 'MySQLdb', 'asyncpg', 'aiohttp',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='牛人Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='牛人Agent',
)
