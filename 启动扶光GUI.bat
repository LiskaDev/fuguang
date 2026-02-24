@echo off
chcp 65001 >nul
echo ============================
echo   扶光系统 - GUI 模式
echo ============================
call D:\conda\condabin\conda.bat activate fuguang
cd /d C:\Users\ALan\Desktop\fuguang
set PYTHONPATH=src
python -m fuguang.gui.app
pause
