@echo off
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\OPENPC\.openclaw\workspace-openpc_ad\crossmart-ops"
"C:\Python314\python.exe" "C:\Users\OPENPC\.openclaw\workspace-openpc_ad\crossmart-ops\backend\scheduled_run.py" >> "C:\Users\OPENPC\.openclaw\workspace-openpc_ad\crossmart-ops\logs\ops_0600.log" 2>&1
