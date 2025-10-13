chcp 65001
@echo off
echo 启动 Claude Code 历史对话管理器...
echo.

cd /d "%~dp0"

python claude_history_manager.py

if errorlevel 1 (
    echo.
    echo 启动失败，请检查Python环境。
    pause
)