# 제품 요구사항 정의서 (PRD - Product Requirement Document)

## 1. 프로젝트 개요 (Overview)
- **제품명:** 정기 웹 크롤링 및 리서치 전문 자료 수집 자동화 시스템 (Research Collection Crawler)
- **목적:** 웹에 공개된 정부기관, 사법·수사기관, 공공기관, 학술단체, 오픈액세스 학술 저장소의 전문 자료(가이드북, 매뉴얼, 지침서, 실무제요, 연구보고서, 학술논문 등)를 정기적으로 추적 및 다운로드하고, 이력을 엑셀/CSV로 관리하며 사용자에게 모바일 최적화 메일을 자동 발송하는 시스템 구축.

---

## 2. 사용자 및 사용 시나리오 (User & Use Cases)
- **타겟 사용자:** 공공·법률·국방·학술 분야 리서치 담당자 및 실무자
- **주요 유스케이스:**
  1. **최초 수집 (First Run):** 2026년 1월 1일부터 2026년 7월 31일까지 발간/업로드된 필수 기관 자료 전수 다운로드 및 이력 정리.
  2. **정기 자동 수집 (Monthly Run):** 매월 1일 오전 09:00에 실행 시점 기준 최근 1개월 이내에 새로 업로드된 자료를 전수 탐색 및 파일 저장.
  3. **목록 관리 및 메일 알림:** 다운로드된 파일 목록을 CSV 및 엑셀(통합 시트 + 월별 시트)로 자동 분류 저장하고, 모바일(갤럭시 폴드7) 최적화 카드형 메일 보고서 수신.

---

## 3. 핵심 기능 요구사항 (Functional Requirements)

### 3.1. 수집 대상 및 범위 (Target Scope)
- **키워드 수집 제한 탈피:** 특정 키워드에 국한하지 않고 설정된 기간 내 필수 기관의 파일(PDF, HWP, HWPX) 전수 수집.
- **필수 수집 기관 도메인:**
  - **학술 분야:** PRISM (`prism.go.kr`), NKIS (`nkis.re.kr`), 국회입법조사처 (`nars.go.kr`), 공공데이터포털 (`data.go.kr`), 알리오 (`alio.go.kr`), RISS (`riss.kr`), 미 육군 작전법센터 (`tjaglcs.army.mil/center/clamo`)
  - **사법 분야:** 경찰청 (`police.go.kr`), 대검찰청 (`spo.go.kr`), 공수처 (`cio.go.kr`), 대법원 (`scourt.go.kr`), 사법연수원 (`jti.scourt.go.kr`), 사법정책연구원 (`jpri.scourt.go.kr`), 법무연수원 (`ioj.go.kr`), 한국형사·법무정책연구원 (`kicj.re.kr`)
  - **국방/작전법 분야:** 미 육군 작전법센터 (CLAMO), 한국국방연구원 (`kida.re.kr`)
  - **분야별 확장:** 교육부 (`moe.go.kr`), 고용노동부 (`moel.go.kr`), 국가인권위원회 (`humanrights.go.kr`)
  - **오픈액세스:** arXiv (`arxiv.org`), SSRN 등

### 3.2. 3단계 접속 및 링크 유효성 검증 엔진 (Validator)
- **1단계 접속 확인:** HTTP Status 200/302 응답 및 정상 접속 확인 (URL 환각 절대 금지).
- **2단계 자료 일치 확인:** 문서 타이틀, 헤더 및 발간 연월 매칭.
- **3단계 무료 다운로드 확인:** 로그인 또는 유료 결제 벽(Paywall) 없는 무료 다운로드 확인.
- **A/B 그룹 분기:**
  - **A그룹:** 영구 직접 PDF 링크 (arXiv, DOI, RAND 등)
  - **B그룹:** 공식 게시글 Landing Page URL (공공기관 게시판, RISS 등 - 세션 ID 포함 일회성 파라미터 링크 금지)

### 3.3. 듀얼 운영 모드 및 일자별 파일 저장 (Storage)
- **1안 모드 (기본):** 검증된 PDF를 `downloads/YYYY-MM-DD/` 일자별 폴더로 자동 다운로드 저장 후 수집 이력 메일 발송.
- **2안 모드:** 파일 다운로드 없이 3단계 검증된 원문 게시글/다운로드 링크 정리 메일 발송.

### 3.4. 이력 관리 (CSV & Excel 다중 시트)
- **`list_download_resources.csv`:** 다운로드 항목 상시 누적 저장 (UTF-8-SIG 적용).
- **`list_download_resources.xlsx`:**
  - `통합 목록` 시트: 전체 누적 데이터 저장.
  - `YYYY-MM 목록` 시트: 발간/수집 일자(예: `2026-01`, `2026-07`, `2026-08`)에 맞춰 월별 시트 자동 생성 및 분리 탭 관리.

### 3.5. 모바일 최적화 메일 발송 (Email Dispatcher)
- 삼성 갤럭시 폴드7 및 모바일 디스플레이 환경에서 가로 스크롤 없이 스캔 가능한 세로형 Card UI HTML 메일 생성.
- SMTP(Gmail App Password 등)를 통한 자동 발송.

### 3.6. 정기 스케줄링 (Scheduler)
- 자동화 주기: **매월 1일 오전 09:00** 실행.
- Windows Task Scheduler 배치 등록 (`scripts/setup_scheduler.bat`) 및 파이썬 데몬 스케줄러 지원.

---

## 4. 비기능 요구사항 (Non-Functional Requirements)
- **안정성:** 예외 처리 (네트워크 타임아웃, SSL 에러 등) 방어 코딩을 통해 프로세스 중단 방지.
- **중복 차단:** SQLite (`database.db`) 기반 URL SHA256 해시 등록으로 중복 파일 다운로드 금지.
- **인코딩 무결성:** Windows CP949 콘솔 인코딩 대응 (`sys.stdout.reconfigure(encoding='utf-8')`).

---

## 5. 시스템 기술 스택 (Tech Stack)
- **Language:** Python 3.11+
- **Libraries:** requests, beautifulsoup4, openpyxl, pandas, pyyaml, schedule, deep-translator
- **Database:** SQLite3
- **Scheduler:** Windows Task Scheduler (`schtasks`) / Python `schedule`
