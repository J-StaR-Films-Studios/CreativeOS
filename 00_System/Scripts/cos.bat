@echo off
REM Use the isolated installation when available; keep the existing launcher usable.
if exist "%~dp0..\..\.cos-venv\Scripts\cos.exe" (
    "%~dp0..\..\.cos-venv\Scripts\cos.exe" %*
) else (
    python "%~dp0manage.py" %*
)