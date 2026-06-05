@echo off
chcp 65001 >nul
title 打包 NEXT 分析仪

echo ====================================
echo   高速线网分析仪 - 打包工具
echo ====================================
echo.
echo 步骤 1: 安装依赖...
pip install PyQt5 matplotlib numpy pyinstaller
if errorlevel 1 (
    echo 安装依赖失败，请确保 Python 已安装
    pause
    exit /b 1
)
echo.
echo 步骤 2: 打包为 exe...
pyinstaller --clean --windowed --name "NEXT_Analyzer" ^
    --add-data "app;app" ^
    --hidden-import PyQt5.sip ^
    --hidden-import matplotlib ^
    --hidden-import numpy ^
    main.py
if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)
echo.
echo ====================================
echo   打包成功！
echo   生成的 exe 位于: dist\NEXT_Analyzer\NEXT_Analyzer.exe
echo ====================================
pause
