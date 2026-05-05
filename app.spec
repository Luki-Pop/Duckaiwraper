# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

project_name = "DuckAI"
script = "app.py"

venv = r"C:\Project\.venv"  # <-- your virtualenv path

# PyQt6 Qt plugins and resources
qt_plugins_src = os.path.join(venv, "Lib", "site-packages", "PyQt6", "Qt", "plugins")
qt_translations_src = os.path.join(venv, "Lib", "site-packages", "PyQt6", "Qt", "translations")
qt_qml_src = os.path.join(venv, "Lib", "site-packages", "PyQt6", "Qt", "qml")
qt_bin_src = os.path.join(venv, "Lib", "site-packages", "PyQt6", "Qt", "bin")
qt_resources_src = os.path.join(venv, "Lib", "site-packages", "PyQt6", "Qt", "resources")

datas = []
if os.path.isdir(qt_plugins_src):
    datas.append((qt_plugins_src, os.path.join("PyQt6", "Qt", "plugins")))
if os.path.isdir(qt_translations_src):
    datas.append((qt_translations_src, os.path.join("PyQt6", "Qt", "translations")))
if os.path.isdir(qt_qml_src):
    datas.append((qt_qml_src, os.path.join("PyQt6", "Qt", "qml")))
if os.path.isdir(qt_bin_src):
    datas.append((qt_bin_src, os.path.join("PyQt6", "Qt", "bin")))
if os.path.isdir(qt_resources_src):
    datas.append((qt_resources_src, os.path.join("PyQt6", "Qt", "resources")))

# Collect PyQt6 package data as well
datas += collect_data_files("PyQt6")

block_cipher = None

a = Analysis(
    [script],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngine",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=project_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=project_name,
)
