@echo off
chcp 65001 > nul
echo =========================================================
echo  웹 크롤링 정기 수집 프로그램 - 윈도우 작업 스케줄러 등록
echo =========================================================

set TASK_NAME=MonthlyResearchCrawler
set SCRIPT_PATH=%~dp0..\main.py
set PYTHON_PATH=python

echo 등록할 작업 이름: %TASK_NAME%
echo 실행할 파이썬 파일: %SCRIPT_PATH%
echo 실행 주기: 매월 1일 오전 09:00

schtasks /create /tn "%TASK_NAME%" /tr "%PYTHON_PATH% \"%SCRIPT_PATH%\" --now" /sc monthly /d 1 /st 09:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [성공] 윈도우 작업 스케줄러에 성공적으로 등록되었습니다.
    echo 매월 1일 오전 09:00에 수집 프로그램이 백그라운드에서 자동 실행됩니다.
) else (
    echo.
    echo [오류] 작업 스케줄러 등록 실패. 배치 파일을 '관리자 권한으로 실행'해 주세요.
)

pause
