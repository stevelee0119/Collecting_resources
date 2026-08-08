# 📋 정기 웹 크롤링 및 리서치 수집 자동화 프로그램 (Research Collection Crawler)

웹에 공개된 정부기관, 사법·수사기관, 국방·학술단체 및 오픈액세스 저장소의 전문 자료(가이드북, 매뉴얼, 지침서, 실무제요, 연구보고서, 학술논문 등)를 추적하고, **설정된 기간 내 업로드된 파일 전체를 자동으로 다운로드 및 관리하는 시스템**입니다.

---

## 🌟 주요 특징 (Key Features)

1. **지능형 발간 기간 조건 수집**
   - **최초 실행 시:** `2026년 1월 1일 ~ 2026년 7월 31일` 기간에 업로드된 파일 전체를 수집합니다.
   - **2회차 정기 실행 이후:** 실행 시점 기준 **최근 1개월(30일) 이내**에 업로드된 최신 자료만 자동 수집합니다.
2. **분야별 필수 검색 기관 전수 수집**
   - 학술(PRISM, NKIS, RISS, 국회입법조사처 등), 사법(경찰청, 대검찰청, 대법원, 사법연수원, 법무연수원 등), 국방/작전법(KIDA, 미 육군 작전법센터 CLAMO), 확장(교육부, 고용노동부, 국가인권위) 및 오픈액세스(arXiv) 등 설정된 기간 내 파일 전수 탐색.
3. **철저한 3단계 링크 검증 (URL 환각 방지)**
   - HTTP 200 접속 확인, 키워드/제목 match, 로그인 없는 무료 다운로드 가능 여부 검증.
   - 세션 ID가 포함된 일회성 파라미터 링크 차단 및 공식 Landing Page (B그룹) 전환.
4. **일자별 파일 저장 & 중복 방지**
   - `downloads/YYYY-MM-DD/` 폴더에 PDF를 일자별로 자동 다운로드 저장.
   - SQLite DB (`database.db`)를 기반으로 이미 다운로드된 자료 중복 배제.
5. **CSV & 엑셀 (통합 시트 + 월별 시트) 다중 탭 관리**
   - `list_download_resources.csv`: 다운로드 이력 상시 기록.
   - `list_download_resources.xlsx`: **`통합 목록` 시트**와 **`YYYY-MM 목록` (월별 탭)**으로 자동 분류 갱신.
6. **모바일 최적화 메일 알림 & 정기 스케줄링**
   - 삼성 갤럭시 폴드7 및 모바일 디스플레이 환경에 최적화된 세로형 Card UI HTML 메일 발송.
   - **매월 1일 오전 09:00** 정기 자동화 실행 (Windows Task Scheduler 지원).

---

## 📂 프로젝트 구조 (Directory Structure)

```text
d:\Collecting_resources\
├── config.yaml                 # 수집 기관, 메일, 스케줄 설정 파일
├── main.py                     # 수집 실행 및 데몬 스케줄러 메인 진입점
├── requirements.txt            # 의존성 패키지 목록
├── PRD.md                      # 제품 요구사항 정의서
├── README.md                   # 프로젝트 사용 설명서
├── database.db                 # SQLite 기반 중복 방지 DB
├── list_download_resources.csv # 수집 자료 누적 목록 CSV
├── list_download_resources.xlsx# 수집 자료 통합 및 월별 시트 Excel
├── downloads/                  # 일자별 PDF 저장 폴더
│   └── 2026-08-08/
├── src/                        # 소스 코드 패키지
│   ├── __init__.py
│   ├── database.py             # 최초 실행 여부 판단 및 DB 관리 모듈
│   ├── query_builder.py        # 필수 기관 도메인 전수 수집 쿼리 생성기
│   ├── validator.py            # 3단계 유효성 검증 & 날짜 필터링 모듈
│   ├── crawler_engine.py       # 필수 기관 전수 탐색 크롤링 엔진
│   ├── downloader.py           # downloads/YYYY-MM-DD/ PDF 저장 모듈
│   ├── excel_manager.py        # CSV 및 Excel 통합/월별 시트 생성기
│   └── mail_sender.py          # 모바일 최적화 HTML 메일 발송 모듈
└── scripts/
    └── setup_scheduler.bat     # 매월 1일 09:00 윈도우 작업 스케줄러 등록 스크립트
```

---

## 🛠️ 설치 방법 (Installation)

1. **저장소 클론 또는 디렉터리 이동:**
   ```cmd
   cd d:\Collecting_resources
   ```

2. **의존성 패키지 설치:**
   ```cmd
   pip install -r requirements.txt
   ```

---

## ⚙️ 설정 방법 (Configuration)

[config.yaml](file:///d:/Collecting_resources/config.yaml) 파일을 열어 메일 계정을 설정합니다:

```yaml
# 정기 자동화 실행 일정 (매월 1일 오전 09:00)
schedule:
  frequency: "monthly"
  day_of_month: 1
  time: "09:00"

# 메일 발송 (SMTP) 설정
email:
  enabled: true
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  sender_email: "your_email@gmail.com"      # 발신자 Gmail 주소
  sender_password: "xxxx xxxx xxxx xxxx"     # Gmail 16자리 앱 비밀번호
  receiver_email: "target_user@gmail.com"   # 수신자 메일 주소
```

---

## 🚀 실행 방법 (Usage)

### 1. 즉시 수집 수동 실행
스케줄 대기 없이 지금 즉시 수집 및 파일 다운로드를 수행하려면 다음 명령을 실행합니다:
```cmd
python main.py --now
```

### 2. 파이썬 데몬 스케줄러 모드 실행
프로세스가 백그라운드에서 매월 1일 오전 09:00에 실행되도록 대기합니다:
```cmd
python main.py --schedule
```

### 3. 윈도우 작업 스케줄러 자동 등록 (권장)
PC 부팅 시 매월 1일 오전 09:00에 수집 프로그램이 자동 실행되도록 윈도우 스케줄러에 등록하려면:
- [scripts/setup_scheduler.bat](file:///d:/Collecting_resources/scripts/setup_scheduler.bat) 파일을 **마우스 우클릭 > '관리자 권한으로 실행'** 하세요.

---

## 📊 결과물 및 리포트 관리

1. **[downloads/](file:///d:/Collecting_resources/downloads)**: `downloads/YYYY-MM-DD/` 하위에 일자별로 다운로드된 PDF 파일이 자동 저장됩니다.
2. **[list_download_resources.xlsx](file:///d:/Collecting_resources/list_download_resources.xlsx)**: 
   - **`통합 목록` 시트:** 전체 누적 수집 목록
   - **`2026-08 목록` 시트:** 월별로 자동 분리된 탭 시트
3. **이메일 리포트:** 메일 수신함에서 삼성 갤럭시 폴드7 등 모바일 디스플레이에 최적화된 세로형 카드 리스트 포맷으로 수집 현황 및 원문/로컬 저장 경로를 확인할 수 있습니다.
