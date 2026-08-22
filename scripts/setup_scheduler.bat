@echo off
chcp 65001 > nul
REM =============================================================================
REM DL-RCIS Windows 작업 스케줄러 등록 (PRD v2.1 16)
REM   - 매일 07:30  일일 증분 수집
REM   - 매월 1일 05:00 월간 정합성 점검
REM 관리자 권한으로 실행하십시오.
REM =============================================================================

setlocal
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

REM 가상환경이 있으면 그 파이썬을 사용합니다.
set "PYTHON_EXE=python"
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"

echo.
echo  프로젝트 경로 : %PROJECT_DIR%
echo  파이썬        : %PYTHON_EXE%
echo.

schtasks /Create /F /TN "DL-RCIS 일일 증분 수집" ^
  /TR "\"%PYTHON_EXE%\" \"%PROJECT_DIR%\main.py\" run --daily" ^
  /SC DAILY /ST 07:30 /RL HIGHEST
if errorlevel 1 goto :failed

schtasks /Create /F /TN "DL-RCIS 월간 정합성 점검" ^
  /TR "\"%PYTHON_EXE%\" \"%PROJECT_DIR%\main.py\" run --reconcile" ^
  /SC MONTHLY /D 1 /ST 05:00 /RL HIGHEST
if errorlevel 1 goto :failed

echo.
echo  [완료] 작업 스케줄러에 등록되었습니다.
echo         확인: schtasks /Query /TN "DL-RCIS 일일 증분 수집"
echo         해제: schtasks /Delete /TN "DL-RCIS 일일 증분 수집" /F
echo.
goto :eof

:failed
echo.
echo  [실패] 등록에 실패했습니다. 관리자 권한으로 다시 실행하십시오.
exit /b 1
