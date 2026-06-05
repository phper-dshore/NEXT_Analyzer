@echo off
REM Launch script for Windows
echo 正在启动高速线网分析仪...
python "%~dp0main.py"
if errorlevel 1 (
    echo 启动失败，请确认已安装 Python 及依赖：
    echo pip install PyQt5 matplotlib numpy
    pause
)
