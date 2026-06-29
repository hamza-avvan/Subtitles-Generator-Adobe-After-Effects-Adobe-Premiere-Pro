# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['generate_subtitle_json.py'],
    pathex=[],
    binaries=[],
    datas=[('ffmpeg.exe', '.'), ('base.pt', 'whisper_models'), ('C:\\Users\\Midnight09x\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\whisper\\assets', 'whisper/assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AfterEffectSubtitlePlugin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='AfterEffectSubtitlePlugin',
)
