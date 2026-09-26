@echo off
REM PowerShell and cmd entry point; Git Bash uses the extensionless sibling.
if exist "%~dp0..\..\.cos-venv\Scripts\cos.exe" (
    "%~dp0..\..\.cos-venv\Scripts\cos.exe" %*
) else (
    python "%~dp0..\Scripts\manage.py" %*
)
