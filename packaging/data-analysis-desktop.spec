from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


spec_directory = Path(SPECPATH).resolve()
project_root = spec_directory.parent
backend_source = project_root / "backend" / "src"
frontend_output = project_root / "frontend" / "dist"
desktop_entry = backend_source / "backend" / "desktop.py"
icon_file = project_root / "icon" / "icon.ico"

if not (frontend_output / "index.html").is_file():
    raise SystemExit("Frontend build is missing. Run `npm.cmd run build` in frontend first.")

dynamic_packages = ["libpysal", "esda", "spreg", "spglm", "mgwr"]
hidden_imports = []
package_data = []
for package in dynamic_packages:
    hidden_imports += collect_submodules(package)
    package_data += collect_data_files(package)

analysis = Analysis(
    [str(desktop_entry)],
    pathex=[str(backend_source)],
    binaries=[],
    datas=[(str(frontend_output), "frontend"), *package_data],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DataEX-G",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file),
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DataEX-G",
)
