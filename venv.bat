@echo off
setlocal

rem スクリプトのあるディレクトリをカレントディレクトリに
cd /d "%~dp0"

rem .venv があるか確認
if exist ".venv\" (
    call :SetupVenv
) else (
    echo .venv が存在しないため新規作成します...
    python -m venv .venv
    if errorlevel 1 (
        echo 仮想環境 .venv の作成に失敗しました。
        goto :eof
    )
    call :SetupVenv
)

goto :eof


:SetupVenv
rem 仮想環境をアクティベート
call ".venv\Scripts\activate.bat"

rem pip を最新化
python -m pip install --upgrade pip

rem ライブラリをインストール
python -m pip install -r requirements.txt

rem コマンドプロンプト立ち上げ
set "CURDIR=%CD%"
start "" cmd /k "cd /d ""%CURDIR%"" ^&^& call .venv\Scripts\activate.bat"

goto :eof
