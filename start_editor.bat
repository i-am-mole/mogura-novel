@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :Launch

set "PYTHON_EXE="
set "PYTHON_ARGS="
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    goto :CreateVenv
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :CreateVenv
)

for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
    if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
)

:CreateVenv
if not defined PYTHON_EXE (
    echo 利用可能なPythonを検出できませんでした。
    pause
    exit /b 1
)

echo 仮想環境 .venv を作成しています...
"%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
if errorlevel 1 (
    echo 仮想環境の作成に失敗しました。
    pause
    exit /b 1
)

echo 必要なライブラリをインストールしています...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ライブラリのインストールに失敗しました。
    pause
    exit /b 1
)

:Launch
".venv\Scripts\python.exe" -c "import markdown" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ライブラリのインストールに失敗しました。
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" "tools\novel_editor.py"
exit /b 0
