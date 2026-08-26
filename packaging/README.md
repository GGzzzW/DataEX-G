# Windows packaging

Run all commands from the repository root on a Windows x64 machine.

## Build the Vue production bundle

```powershell
cd frontend
npm.cmd run build
cd ..
```

## Build the desktop application folder

```powershell
uv run --project backend pyinstaller --noconfirm --clean packaging/data-analysis-desktop.spec
```

The distributable application is created at:

```text
dist/DataEX-G/DataEX-G.exe
```

Distribute the entire `DataEX-G` folder. Do not copy only the EXE.

## Automated smoke test

```powershell
$env:DATA_ANALYSIS_DESKTOP_SMOKE_TEST = "1"
dist/DataEX-G/DataEX-G.exe
$result = $LASTEXITCODE
Remove-Item Env:DATA_ANALYSIS_DESKTOP_SMOKE_TEST
exit $result
```

The smoke test starts the packaged local API, checks `/health` and the bundled Vue
page, and then exits without opening the GUI.

## Release checks

- Test on a clean Windows 10/11 x64 machine without Python, Node.js, or uv.
- Test CSV and XLSX upload/export with Chinese paths and filenames.
- Run cleaning, all regression methods, and all spatial methods.
- Confirm closing the window stops `DataEX-G.exe`.
- Ensure Microsoft Edge WebView2 Runtime is installed on the target machine.
