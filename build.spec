# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 单文件打包配置
# 使用方法: pyinstaller build.spec

import os
import glob
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

def collect_files(pattern, dest_folder='.'):
    """安全地收集文件，如果文件不存在则跳过"""
    files = []
    try:
        matches = glob.glob(pattern, recursive=True)
        for match in matches:
            if os.path.isfile(match):
                files.append((match, dest_folder))
    except Exception:
        pass
    return files

# 收集所有资源文件
datas = []

# 添加核心Python文件 - 更新为PyQt版本的文件
core_files = [
    'gui.py',
    'core.py',
    'config.py',
    'clipboard_utils.py',
    'sentiment_analyzer.py',
    'pyqt_tabs.py',
    'pyqt_hotkeys.py',
    'pyqt_setting.py',
    'pyqt_style.py',
    'pyqt_about.py',
    'path_utils.py',
    'image_processor.py',
    'update_checker.py',

    'ui_pyqt_main.py',
    'ui_pyqt_components.py',
    'ui_pyqt_setting.py',
    'ui_pyqt_style.py',
    'ui_pyqt_about.py'
]

for file in core_files:
    if os.path.exists(file):
        datas.append((file, '.'))


# 收集证书文件
try:
    certifi_data = collect_data_files('certifi')
    datas.extend(certifi_data)
except:
    pass

# 排除不需要的库 - 增加更多排除项以减小体积
excludes = [
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'test',
    'unittest',
    'pydoc',
    'doctest',
    'setuptools',
    'pip',
    'jupyter',
    'IPython',
    'notebook',
    'rich',
    'pytest',
    'sphinx',
    'bz2',
    'lzma',
    'sqlite3',
    'tkinter',
    'tkinter.test',
    'tkinter.ttk.test',
    'PIL.ImageFilter',
    'PIL.ImageEnhance',
]

# 添加PySide6相关的隐藏导入
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui', 
    'PySide6.QtWidgets'
]

a = Analysis(
    ['gui.py'],  # 修改入口文件为gui.py
    pathex=[os.getcwd()],
    binaries=[
        ('Image_Processor.dll', '.'),
        ('SDL2_image.dll', '.'),
        ('SDL2_ttf.dll', '.'),
        ('SDL2.dll', '.'),
        ('libwebpdemux-2.dll', '.'),
        ('libwebp-7.dll', '.'),
    ],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='魔裁文本框',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)