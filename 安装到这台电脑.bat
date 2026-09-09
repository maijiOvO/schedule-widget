@echo off
cd /d "%~dp0"
echo.
echo   2026 Fall 日程组件 —— 安装到这台电脑
echo   ----------------------------------------
echo.

where pythonw >nul 2>&1
if errorlevel 1 goto nopython
echo   [1/3] 检查 Python ... OK

python -c "import tkinter" 2>nul
if errorlevel 1 goto notk
echo   [2/3] 检查 tkinter ... OK

python widget.py --startup
if errorlevel 1 goto failed
echo   [3/3] 已设为开机自启

start "" pythonw widget.py
echo.
echo   完成。组件已经在屏幕右上角了，可以拖到你想要的位置。
echo   右键组件有菜单：立即刷新 / 总在最前 / 退出。
echo.
pause
exit /b 0

:nopython
echo   没有找到 Python。
echo.
echo   去 https://www.python.org/downloads/ 装一个 Python 3.9 以上版本，
echo   安装时务必勾选 "Add python.exe to PATH"，装完重新运行本文件。
echo.
pause
exit /b 1

:notk
echo   Python 装了，但缺少 tkinter。
echo   重新运行 Python 安装程序，选 Modify，勾上 "tcl/tk and IDLE"。
echo.
pause
exit /b 1

:failed
echo   设置开机自启失败。可以手动双击 启动组件.vbs 来运行。
echo.
pause
exit /b 1
