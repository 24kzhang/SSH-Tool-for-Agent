# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH)

a = Analysis(
    ["app.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ("assets", "assets"),
        ("README.md", "."),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQmlModels",
        "PySide6.QtQmlWorkerScript",
        "PySide6.QtQuick",
        "PySide6.QtPdf",
        "PySide6.QtVirtualKeyboard",
        "PySide6.QtOpenGL",
        "PySide6.QtSvg",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
    ],
    noarchive=False,
    optimize=0,
)


def keep_packaged_file(item):
    name = item[0].replace("\\", "/")
    basename = Path(name).name
    excluded_qt_files = {
        "opengl32sw.dll",
        "Qt6Quick.dll",
        "Qt6Qml.dll",
        "Qt6Pdf.dll",
        "Qt6OpenGL.dll",
        "Qt6Network.dll",
        "QtNetwork.pyd",
        "Qt6QmlModels.dll",
        "Qt6Svg.dll",
        "Qt6VirtualKeyboard.dll",
        "Qt6QmlMeta.dll",
        "Qt6QmlWorkerScript.dll",
        "qdirect2d.dll",
        "qoffscreen.dll",
        "qminimal.dll",
        "qtvirtualkeyboardplugin.dll",
        "qtuiotouchplugin.dll",
        "qnetworklistmanager.dll",
        "qsvgicon.dll",
        "qgif.dll",
        "qicns.dll",
        "qjpeg.dll",
        "qpdf.dll",
        "qsvg.dll",
        "qtga.dll",
        "qtiff.dll",
        "qwbmp.dll",
        "qwebp.dll",
        "qcertonlybackend.dll",
        "qopensslbackend.dll",
        "qschannelbackend.dll",
    }
    kept_translations = {
        "qtbase_zh_CN.qm",
        "qt_zh_CN.qm",
        "qtbase_en.qm",
        "qt_en.qm",
    }
    if name.startswith("PySide6/translations/"):
        return basename in kept_translations
    return basename not in excluded_qt_files


a.binaries = [item for item in a.binaries if keep_packaged_file(item)]
a.datas = [item for item in a.datas if keep_packaged_file(item)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RemoteTool",
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
    icon=str(project_root / "assets" / "remote-tool.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RemoteTool",
)
