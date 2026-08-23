# 제품 요구사항 정의서 (PRD - Product Requirement Document)

## 0. 문서 정보
- **제품명:** 국방·법률·공공·학술 리서치 자동수집·요약·알림 시스템
- **영문명:** Defense & Legal Research Collection and Intelligence System (DL-RCIS)
- **문서 버전:** v2.1
- **기준일:** 2026-08-22
- **주요 사용자:** 군법무관, 법무부사관, 법무 분야 군무원, 법률·국방 교육 담당자, 공공·학술 리서치 담당자
- **핵심 설계 원칙:** `공식 API/OAI-PMH/RSS 우선 → 허용된 공개 웹 접근 → 링크 보존` 순으로 수집하며, 로그인·유료결제·CAPTCHA·접근통제·자동화 금지 정책을 우회하지 않는다.

---

## 1. 프로젝트 개요 (Overview)

### 1.1. 목적
웹에 공개된 정부기관, 사법·수사기관, 공공기관, 연구기관, 학술단체, 오픈액세스 저장소의 전문 자료를 자동으로 탐색·수집하고, 새로 공개되거나 변경된 자료를 매일 식별하여 다음 기능을 제공한다.

1. **국방·법률·공공·학술 자료의 지속적 수집**
2. **허용된 경우 PDF/HWP/HWPX 등 원문 자동 다운로드**
3. **자동 다운로드가 허용되지 않는 경우 공식 Landing Page와 영구식별자(DOI 등) 보존**
4. **다운로드 일자를 파일명 접두사로 기록**하여 파일 탐색성과 시계열 정렬성 확보
5. **일자별 수집 목록(Manifest) 유지 + 주제별 최종 파일 보관**
6. **새로운 자료의 핵심 요약·교육 활용 포인트·중요도 분석**
7. **이메일 또는 공식 메시징 채널을 통한 일일 업데이트 알림**
8. **중복·개정판·동일 논문의 여러 출처를 식별하여 하나의 연구자산으로 관리**

### 1.2. 기존 PRD 대비 핵심 변경점
- 매월 1회 중심 구조를 **매일 증분 수집 + 월 1회 정합성 점검** 구조로 변경
- DuckDuckGo HTML 검색결과 수집 의존 구조를 제거하고 **공식 API/OAI-PMH/RSS/기관 검색 API 우선**으로 전환
- `downloads/YYYY-MM-DD/`에 최종 보관하던 구조를 **일자별 Manifest + 주제별 최종 저장소**로 변경
- URL 단위 중복 제거에서 **DOI/공식 ID + 파일 SHA256 + 정규화 텍스트 해시**를 결합한 다단계 중복관리로 고도화
- SSRN·RISS 등 접근정책이 복잡한 소스는 **메타데이터 수집과 원문 다운로드를 분리**
- 새 자료에 대한 **한국어 요약, 중요도, 법무교육 활용성, 원문 근거범위**를 함께 기록
- 영문 학술DB에서는 한국어 검색어를 그대로 보내지 않고 **군사법·국제법·법률 분야의 검수된 영문 용어사전으로 번역·확장**하여 검색
- API Key/OAuth/기관승인 등이 필요한 연결원은 구현 시 **별도 `API_발급_연동_가이드.md`를 반드시 생성·갱신**하여 비개발자도 발급 절차를 따라갈 수 있도록 함

---

## 2. 사용자 및 주요 사용 시나리오 (Users & Use Cases)

### 2.1. 주요 사용자
- 군법무관 및 군사법·국방법 연구자
- 법무부사관 및 법무 분야 군무원
- 법무교육 과정 기획·교수 인력
- 국방행정·인사·감찰·수사·인권 관련 법률 실무자
- 공공기관 법률·정책 연구 담당자

### 2.2. 주요 유스케이스

#### UC-01. 초기 백필(Backfill)
- 설정된 시작일~현재일까지 주요 출처의 과거 자료를 수집한다.
- 초기 기본 범위 예시: `2026-01-01 ~ 실행일`.
- **전문기관형 소스**는 해당 기간 전체 자료를 대상으로 할 수 있으나, SSRN·RISS·OpenAlex 등 대규모 범용 학술DB는 설정된 국방·법률 주제에 한정한다.

#### UC-02. 일일 증분 수집(Daily Incremental Run)
- 매일 설정된 시각에 전일 실행 이후 신규·수정된 자료를 조회한다.
- 등록 지연을 고려하여 기본적으로 **최근 3일 look-back** 범위를 다시 확인하고 중복 제거한다.
- 실행시각은 `config.yaml`에서 변경 가능하며 KST(`Asia/Seoul`)를 명시적으로 사용한다.

#### UC-03. 월간 정합성 점검(Monthly Reconciliation)
- 매월 1회 최근 30~45일 범위를 재조회하여 API 지연 등록, 수정본, 누락 자료를 보정한다.
- 일일 수집 실패가 있었던 소스에 대해 재시도한다.

#### UC-04. 주제별 지식저장소 구축
- 수집된 파일은 물리적으로 **주제별 폴더에 최종 저장**한다.
- 일자별로 파일을 중복 저장하지 않고, 해당 일자에 무엇을 수집했는지는 **Manifest**로 관리한다.

#### UC-05. 일일 브리핑
- 신규 자료가 있는 경우 제목·출처·발행일·수집일·핵심요약·중요도·교육 활용 포인트·원문 링크를 이메일 또는 설정된 메시징 채널로 전송한다.
- 신규 자료가 없으면 “신규 중요 자료 없음” 또는 무발송 모드를 선택할 수 있다.

---

## 3. 수집 범위와 주제 체계 (Scope & Taxonomy)

### 3.1. 기본 주제 분류
최종 저장 및 검색을 위해 최소 다음 분류를 사용한다.

1. `01_군사법_군사사법`
   - 군사재판, 군검찰, 군사경찰, 군형사절차, 징계절차
2. `02_군인사_복무_징계`
   - 인사, 보직, 진급, 전역, 복무, 징계, 소청
3. `03_국방정책_행정법`
   - 국방행정, 조직, 규제, 국가배상, 행정쟁송
4. `04_국방계약_조달법제`
   - 국가계약, 국방계약, 방산 관련 법제·정책·분쟁
5. `05_형사_수사_사법`
   - 형법, 형사소송, 수사절차, 증거법, 사법제도
6. `06_헌법_인권`
   - 기본권, 군인권, 국가인권위원회, 인권정책
7. `07_국제법_작전법_국제인도법`
   - 국제법, 국제인도법, 무력분쟁법의 법률·정책 연구
8. `08_AI_법률AI_디지털법`
   - 법률AI, AI 거버넌스, 공공부문 AI, 데이터·알고리즘 규율
9. `09_법무교육_교육방법론`
   - 법학교육, 군 교육, 성인교육, AI 리터러시
10. `10_비교법_해외법제`
11. `90_복수주제`
12. `99_미분류_검토필요`

### 3.2. 수집 모드
각 소스는 다음 중 하나의 모드로 등록한다.
- **FULL:** 전문기관의 특정 기간 자료 전수 메타데이터·허용 원문 수집
- **QUERY:** 대규모 범용 학술DB에서 주제·키워드·필터 기반 수집
- **FEED:** RSS/Atom/OAI-PMH datestamp 기반 최신자료 수집
- **LINK_ONLY:** 원문 자동 저장 대신 메타데이터와 공식 링크만 저장
- **OA_RESOLVER:** DOI 등을 받아 합법적인 오픈액세스 원문 위치를 탐색

### 3.3. 국내 학술·법률 검색 필수 키워드 베이스라인
국내 KCI·RISS·ScienceON·AccessON·기관 리포지터리 등에서 `QUERY` 방식으로 탐색할 때에는 아래 키워드를 **최소 기본사전(seed terms)** 에 포함한다. 운영 중 추가·삭제할 수 있도록 코드에 하드코딩하지 않고 `config/search_terms.yaml`에서 관리한다.

#### 필수 포함 키워드
- 포렌식
- 디지털포렌식
- 위법수집증거
- 위법수집증거배제법칙
- 판결
- 판례
- 방위사업법
- 방위사업
- 군사기밀보호법
- 군사기밀
- 군사기지
- 군사기지 및 군사시설 보호법
- 사법제도
- 군검찰
- 군사경찰
- 증거능력
- 법률전
- 군검사
- 형사소송법
- 군사법원
- 통합방위법

#### 국내 검색어 확장 규칙
- 띄어쓰기·붙여쓰기·약칭 차이를 함께 관리한다.
- 법령명은 정식 명칭과 실무상 약칭을 함께 검색한다.
- `판결`과 `판례`, `포렌식`과 `디지털포렌식`처럼 의미가 겹치더라도 검색 누락 방지를 위해 별도 seed term으로 유지한다.
- 키워드별로 `exact_phrase`, `synonyms`, `related_terms`, `exclude_terms`, `topic_id`, `priority`를 관리한다.
- 단일 키워드가 과도한 잡음을 발생시키면 기관·학술분야·연도·문서유형 필터와 결합한다.

### 3.4. 검색어 사전의 변경관리
- 검색어 사전은 버전(`dictionary_version`)을 부여한다.
- 변경일, 변경자, 변경사유, 추가·삭제된 용어를 기록한다.
- 일일 Manifest에는 어떤 검색어/사전 버전으로 자료가 발견되었는지 남긴다.
- 분기별로 누락·오탐 샘플을 검토하여 검색어를 보정한다.

---

## 4. 수집 소스 전략 (Source Strategy)

### 4.1. 소스 우선순위 원칙
수집 안정성·재현성·법적 리스크를 고려하여 다음 우선순위를 강제한다.

1. **공식 Open API / REST API**
2. **OAI-PMH**
3. **RSS / Atom Feed**
4. **공식 Sitemap / 공개 다운로드 목록**
5. **기관 웹페이지의 허용된 HTML 수집**
6. **라이선스된 검색 API를 통한 보조 발견**
7. **자동수집이 불명확하거나 금지된 경우 LINK_ONLY**

> 검색엔진의 HTML 결과 페이지를 직접 스크래핑하는 방식을 핵심 탐색수단으로 사용하지 않는다.

### 4.2. 국내 학술·정책 핵심 소스

#### A. KCI (한국학술지인용색인) — 최우선
- **접근방식:** Open API + OAI-PMH
- **활용:** 국내 학술논문 메타데이터, DOI, 초록, 키워드, 인용정보, 등록·수정일 기반 증분수집
- **수집모드:** `QUERY + FEED`
- **원문:** KCI가 제공하는 공개 원문 또는 OA 위치가 확인된 경우만 다운로드
- **비고:** OAI-PMH는 별도 키 없이 사용할 수 있는 공개 메타데이터 경로로 우선 검토

#### B. RISS — 중요하나 접근정책 분리
- **접근방식:** 가능한 경우 RISS Open API 활용 신청·승인 후 메타데이터 수집
- **대안:** 승인되지 않은 경우 RISS를 직접 대량 크롤링하지 않고 공식 Landing Page를 참조 정보로 보존
- **원문:** RISS 검색결과가 연결하는 KCI·ScienceON·기관 리포지터리·기타 OA 제공처에서 합법적인 공개본을 우선 확보
- **수집모드:** `QUERY / LINK_ONLY`
- **원칙:** RISS 화면에서 보이는 “원문있음”과 실제 자동 다운로드 권한을 동일시하지 않는다.

#### C. ScienceON / AccessON (KISTI)
- **접근방식:** ScienceON API Gateway의 공개 API, AccessON의 오픈액세스 검색 활용
- **활용:** 국내외 학술논문·연구보고서의 메타데이터 및 OA 원문 후보 탐색
- **수집모드:** `QUERY + OA_RESOLVER`

#### D. NKIS 국가정책연구포털
- **접근방식:** 인증키 기반 공식 Open API
- **활용:** 정부출연연구기관의 연구보고서, 정기간행물, 정책·연구자료, 세미나자료
- **수집모드:** `FULL + QUERY`

#### E. PRISM 정책연구관리시스템
- **접근방식:** 공공데이터포털·공식 제공 인터페이스 우선, 보조적으로 허용된 기관 웹 탐색
- **활용:** 중앙·지방정부 정책연구용역 보고서
- **수집모드:** `FULL + QUERY`

#### F. 국가법령정보센터 공동활용
- **접근방식:** 공식 Open API
- **활용:** 법령, 행정규칙, 판례, 법령 변경이력, 별표·서식 등
- **수집모드:** `FULL + QUERY`
- **특이사항:** 개정일·시행일·공포일을 각각 별도 필드로 저장하여 “신규 법령”과 “개정 법령”을 구분

#### G. 디지털집현전 (국가지식정보 통합플랫폼) *(2026-08-23 추가)*
- **접근방식:** 인증키 기반 공식 Open API (서비스 신청·승인 후 명세 발급)
- **활용:** 국가기관·지방자치단체·공공기관이 생산한 지식정보의 통합 메타데이터
  (제목·날짜·저자·요약·주제어). 기관별 소스가 미확정인 영역의 공백을 메운다.
- **수집모드:** `FULL + QUERY`
- **특이사항:** 여러 기관 자료를 모으는 **집계 플랫폼**이므로 KCI·NKIS·국가법령정보 등
  개별 소스와 동일 자료가 중복 유입될 수 있다. 중복은 §11 다단계 중복제거로 처리하고,
  원문은 원 기관 사이트에 있으므로 기본 정책은 링크 보존(`link_only`)으로 둔다.

### 4.3. 국내 기관형 법률·국방 소스
다음 기관은 해당 기관의 공식 공개자료실·연구보고서·간행물을 대상으로 Source Adapter를 별도 구성한다.

- 국회입법조사처
- 대법원 및 사법정책연구원
- 법무연수원
- 한국형사·법무정책연구원
- 국가인권위원회
- 한국법제연구원(NKIS 연계 우선)
- 한국국방연구원(KIDA)
- 국방부 공개 법령·정책·간행물 영역
- 군사법·작전법 관련 해외 공공 법률교육기관의 공개 법률자료

기관별로 API/RSS/OAI-PMH가 없으면 `robots.txt`, 이용약관, 저작권정책, 공개 다운로드 구조를 사전 점검한 후 개별 Adapter를 사용한다.

### 4.4. 해외 학술 소스 — 필수 추가

#### A. Crossref
- **역할:** DOI 메타데이터의 기준축
- **활용:** 제목·저자·학술지·발행일·DOI 정규화, 중복 판별
- **수집모드:** `QUERY / IDENTIFIER_RESOLVER`

#### B. OpenAlex
- **역할:** 대규모 학술 그래프 및 주제·인용·OA 메타데이터 탐색
- **활용:** 법률AI·공공정책·국제법 등 영문 연구 동향 탐색, DOI·OA 위치·관련 논문 확장
- **수집모드:** `QUERY`
- **구현:** 대량 결과는 cursor 방식, 전체 데이터가 필요할 경우 API 전수 순회가 아니라 공식 snapshot 검토

#### C. Semantic Scholar
- **역할:** 논문·저자·인용관계·PDF URL·초록 등의 보조 학술 그래프
- **활용:** 중요 논문의 관련연구·인용관계 탐색과 최신 논문 보강
- **수집모드:** `QUERY`

#### D. CORE
- **역할:** 오픈액세스 논문 원문 확보의 핵심 소스
- **활용:** 메타데이터와 공개 full text를 API로 조회
- **수집모드:** `QUERY + OA_RESOLVER`

#### E. Unpaywall
- **역할:** DOI 기반 합법적 OA 위치 확인
- **활용:** `best_oa_location`, `url_for_pdf`, 라이선스, 버전 정보를 이용하여 유료 출판사 페이지 대신 합법적인 공개본 탐색
- **수집모드:** `OA_RESOLVER`

#### F. DOAJ
- **역할:** 검증된 오픈액세스 저널·논문 메타데이터
- **접근방식:** API + OAI-PMH
- **수집모드:** `QUERY + FEED`

#### G. arXiv
- **역할:** AI·컴퓨터과학·통계 등 빠르게 업데이트되는 연구의 preprint 수집
- **접근방식:** 공식 API/Atom 및 공개 원문
- **수집모드:** `QUERY + FEED`

#### H. SSRN — 법학·사회과학 핵심 소스
- **중요성:** 법학·사회과학 preprint·working paper 확보에 반드시 포함
- **기본전략:** SSRN 검색화면을 대량 스크래핑하는 대신 OpenAlex·Crossref·Semantic Scholar 등에서 SSRN DOI/논문을 먼저 발견한 뒤 SSRN 공식 Abstract Page를 canonical source로 연결
- **원문 다운로드:** 공개 다운로드 버튼이 존재하더라도 해당 시점의 SSRN/Elsevier 이용조건과 논문별 라이선스를 점검하여 자동 다운로드 허용 여부를 결정
- **불명확하거나 제한되는 경우:** `LINK_ONLY`로 저장하고 사용자에게 원문 링크를 제공
- **금지:** 로그인 우회, CAPTCHA 회피, 브라우저 지문 우회, 세션·토큰 추출을 통한 자동 다운로드

#### I. Zenodo 등 범용 오픈 리포지터리
- **역할:** 연구보고서, 데이터셋, 프리프린트, 기관 연구성과 보강
- **접근방식:** 공식 API가 있는 저장소를 우선 등록
- **수집모드:** `QUERY + OA_RESOLVER`

### 4.5. 사용량·규모를 고려한 소스 보강 근거 (2026-08-22 기준 검토)
- **RISS:** KERIS가 국내 최대 학술연구정보 통합플랫폼으로 설명하는 핵심 국내 학술 게이트웨이이므로 유지한다.
- **SSRN:** 약 177만 건 이상의 full-text paper와 최근 12개월 5천5백만 회 이상의 다운로드 규모를 보이는 법학·사회과학 핵심 소스이므로 필수 유지한다.
- **Semantic Scholar:** 약 2억 건 이상의 논문과 수십억 건의 인용관계를 제공하므로 영문 학술 탐색용 보조축으로 추가한다.
- **CORE:** 수억 건의 검색 가능 학술레코드와 수천만 건 규모의 직접 full text를 제공하므로 OA 원문확보 핵심 소스로 추가한다.
- **ResearchGate 등 대규모 연구자 플랫폼:** 높은 이용량은 발견채널로서 의미가 있으나, 저작권·자동수집 정책과 원문 버전의 불확실성 때문에 자동 다운로드 핵심 소스로 사용하지 않고 필요 시 사람의 수동 탐색 참고채널로 한정한다.

---

## 5. Source Registry 및 접근정책 관리

모든 출처를 `config/sources.yaml`에 등록하고 최소 다음 정보를 유지한다.

```yaml
source_id: kci
name: Korea Citation Index
base_domain: kci.go.kr
mode: [QUERY, FEED]
access_methods:
  - type: OAI_PMH
    auth_type: NONE
    credential_required: false
  - type: OPEN_API
    auth_type: API_KEY
    credential_required: true
    credential_env_var: KCI_API_KEY
credential_guide_required: true
auth_docs_url: OFFICIAL_SOURCE_ONLY
robots_policy: respect
terms_checked_at: 2026-08-22
download_policy: oa_only
rate_limit_rps: 0.5
lookback_days: 3
priority: 1
query_language: ko
enabled: true
```

### 필수 정책 필드
- `source_id`
- `access_methods[]`
- `access_methods[].type`
- `access_methods[].auth_type`: `NONE / API_KEY / OAUTH2 / SERVICE_ACCOUNT / INSTITUTION_APPROVAL / OTHER`
- `access_methods[].credential_required`
- `access_methods[].credential_env_var`
- `credential_guide_required`
- `auth_docs_url` — 구현 시 반드시 공식 개발자/기관 문서 URL로 확정
- `query_language`: `ko / en / multilingual`
- `terms_checked_at`
- `robots_policy`
- `download_policy`: `allowed / oa_only / link_only / manual_review`
- `rate_limit_rps`
- `max_concurrency`
- `retry_policy`
- `contact_or_policy_url`
- `last_success_at`
- `last_policy_review_at`

### 정책 재검토
- 최소 분기 1회 또는 HTTP 403/429/접근정책 변경 감지 시 재검토
- 정책이 불명확하면 자동 다운로드를 중지하고 `LINK_ONLY`로 자동 강등

### 5.1. API·인증정보 발급 가이드 산출물 — 필수
프로그램 구현 단계에서 API Key, OAuth 2.0 Client ID, 서비스계정, 기관 승인, 이메일 등록 등 **사전 발급·승인이 필요한 모든 Source Connector를 자동 식별**하고 다음 별도 문서를 생성한다.

#### 필수 산출물
```text
docs/API_발급_연동_가이드.md
```

필요 시 비개발자 확인용으로 동일 내용을 Excel(`docs/API_발급_연동_가이드.xlsx`)로 병행 생성할 수 있다.

#### 소스별 필수 기재항목
1. 서비스/기관명
2. 사용하려는 API 또는 인증방식
3. API Key·OAuth·기관승인 필요 여부
4. **공식 발급/신청 페이지**
5. 계정 생성 필요 여부
6. 신청 메뉴까지의 단계별 경로
7. 신청서에 기재해야 하는 서비스 목적 예시
8. 승인 필요 여부 및 공식적으로 안내된 승인 절차
9. 무료/유료 여부와 공식 쿼터·Rate Limit
10. 필요한 OAuth Scope 또는 권한
11. Redirect URI/Callback URL 필요 여부
12. 발급 후 프로그램에 넣어야 하는 환경변수명
13. 최소 동작 확인용 테스트 방법
14. 키 만료·갱신·회수 방법
15. 이용약관·저작권·자동수집 관련 주의사항
16. 공식 문서 최종 확인일(`verified_at`)

#### 구현 시 반드시 점검할 인증 대상군
- KCI Open API — Open API Key 발급 여부와 절차 확인; OAI-PMH는 별도 인증 필요 여부를 독립 확인
- RISS Open API — 신청 가능 범위, 승인조건, 인증키 발급방법 확인
- NKIS Open API — 회원가입·활용신청·기관검토·인증키 발급절차 확인
- ScienceON API Gateway / AccessON — API별 인증방식과 이용조건 확인
- 국가법령정보 공동활용 — 공동활용 신청·식별자/인증방식 확인
- OpenAlex — 구현 시점 API Key 및 요금/무료 한도 확인
- Semantic Scholar — API Key 필요 여부 및 호출량 정책 확인
- CORE — API 인증 및 원문 이용조건 확인
- Crossref / DOAJ / arXiv / Unpaywall — Key 미요구형이라도 이메일·식별자·정책상 요구값 확인
- Gmail API — Google Cloud 프로젝트, OAuth 동의화면, OAuth Client, Scope, Refresh Token 절차 확인
- 향후 추가되는 모든 Connector

#### 보안 원칙
- 실제 API Key, Client Secret, Refresh Token은 가이드 문서에 절대 기록하지 않는다.
- 가이드에는 환경변수명만 기록한다. 예: `KCI_API_KEY`, `OPENALEX_API_KEY`, `GMAIL_CLIENT_SECRET_FILE`.
- 비밀정보는 `.env`(Git 제외), OS Secret Store 또는 배포환경 Secret Manager에 저장한다.
- `.env.example`에는 변수명과 설명만 넣고 실제 값은 넣지 않는다.

#### 최신성 원칙
API 발급·인증 방식은 변경될 수 있으므로 **실제 Connector 구현 직전 공식 문서를 다시 확인**한다. 블로그·카페·개인 튜토리얼은 보조자료로만 사용하고, 발급절차·쿼터·가격·권한은 공식 문서를 기준으로 작성한다.

---

## 6. 자료 탐색 및 수집 파이프라인 (Discovery & Ingestion)

### 6.1. 처리 순서
1. **Scheduler 실행**
2. Source Registry에서 활성 소스 목록 로드
3. 소스별 공식 API/OAI/RSS 호출
4. 메타데이터 정규화
5. 접근정책·라이선스 검사
6. DOI/공식 ID 기반 1차 중복 판별
7. OA Resolver 실행(CORE/Unpaywall/OpenAlex 등)
8. 다운로드 후보 URL 검증
9. 허용된 원문만 다운로드
10. 파일 해시·텍스트 해시 계산
11. 문서 형식·무결성 검사
12. 주제 분류 및 중요도 산정
13. 주제별 최종 저장소로 이동
14. 일자별 Manifest 및 DB 기록
15. 요약 생성
16. 이메일/메신저 브리핑 발송

### 6.2. 검색엔진 사용 원칙
- 검색엔진은 **누락 발견용 최후 보조수단**으로만 사용한다.
- 검색결과 HTML을 크롤링하지 않고 이용조건이 명확한 공식/상용 Search API를 사용한다.
- 검색 결과에서 발견한 자료도 반드시 원 출처의 접근정책을 다시 검사한다.

### 6.3. 대규모 범용 학술DB 탐색 방식
SSRN·OpenAlex·Semantic Scholar·RISS 등에서는 전체 논문을 전부 내려받지 않는다.

#### 1차 검색
- 국방·군사법·군인사·군사사법·인권·국제법·AI법·법률AI·법학교육 등 관리 키워드
- 한국어/영어 동의어 사전 병행

#### 2차 확장
- DOI 기준 인용/피인용 문헌
- 동일 저자 최근 연구
- 유사 주제 문헌
- 동일 학술지의 최근호

#### 3차 우선순위 필터
`relevance_score >= threshold`인 자료만 원문 다운로드 대상으로 선정한다.

### 6.4. 다국어 검색어 변환·확장 엔진 (Multilingual Query Expansion) — 필수
해외 영문 학술소스에서 한국어 검색어를 그대로 전송하여 검색 누락이 발생하지 않도록 **검색 직전에 영어 학술·법률 용어로 변환·확장**한다.

#### 처리 원칙
1. `query_language: en`으로 등록된 소스에는 한국어 seed term을 그대로 핵심 검색어로 보내지 않는다.
2. 한국어 입력어를 `config/search_terms.yaml`의 **검수된 한·영 대응사전**에서 먼저 조회한다.
3. 단순 직역 하나가 아니라 법률·국제법·군사법 문헌에서 실제 사용하는 **정식 용어, 동의어, 약어, 조약명, 관련 법개념**을 복수의 검색어로 확장한다.
4. 사전에 없는 용어만 번역모델/LLM을 보조적으로 사용하고, 자동 생성된 용어는 `machine_suggested=true`로 표시하여 검수 대상에 포함한다.
5. 의미가 여러 개인 한국어는 하나로 단정하지 않고 복수 후보를 생성한다.
6. 영문 소스가 Boolean/phrase 검색을 지원하면 정확구문(`"..."`)과 OR 그룹을 활용한다.
7. 검색에 실제 사용한 영문 Query 전체를 DB와 Manifest에 남겨 재현 가능하게 한다.

#### 안전한 예시
```yaml
- canonical_ko: 작전법
  en_terms:
    - operational law
  topic_id: 07_국제법_작전법_국제인도법

- canonical_ko: 해양법
  en_terms:
    - law of the sea
    - maritime law
  related_terms:
    - UNCLOS
  topic_id: 07_국제법_작전법_국제인도법

- canonical_ko: 제네바협약
  en_terms:
    - Geneva Conventions
  topic_id: 07_국제법_작전법_국제인도법
```

> 기타 사용자가 등록한 국방·국제인도법·AI 관련 학술 주제도 같은 방식으로 **학술·법률 문헌 탐색 목적의 용어사전**을 통해 변환한다.

### 6.5. `search_terms.yaml` 권장 스키마
```yaml
dictionary_version: 2026.08.22-1
terms:
  - canonical_ko: 작전법
    ko_variants: [작전 법]
    en_terms: [operational law]
    en_acronyms: []
    related_terms: []
    exclude_terms: []
    source_scope: [domestic, international]
    topic_id: 07_국제법_작전법_국제인도법
    priority: 1
    human_verified: true
    reviewed_at: 2026-08-22
```

### 6.6. 검색어 품질관리
- 영문 검색 결과 샘플을 정기 검수하여 번역은 맞지만 학술적으로 사용되지 않는 표현을 제거한다.
- `precision`뿐 아니라 `recall`을 평가하여 특정 번역 하나 때문에 핵심 논문이 누락되지 않도록 한다.
- 신규 논문에서 반복적으로 등장하는 전문용어는 후보사전에 자동 제안하되 사람 검수 후 활성화한다.
- 국내·해외 검색어 사전은 같은 `canonical concept`에 연결하여 언어가 달라도 동일 주제로 집계한다.

---

## 7. 원문 접근·다운로드 정책 (Download Policy)

### 7.1. 다운로드 허용 조건
다음 조건을 모두 충족하는 경우 자동 다운로드할 수 있다.
1. 접근정책상 자동 접근이 허용되거나 공식 API/다운로드 엔드포인트가 제공됨
2. 로그인·결제·CAPTCHA 등 접근통제를 우회하지 않음
3. 공개 다운로드 또는 OA 라이선스가 확인됨
4. 최종 응답이 실제 문서이며 MIME Type·파일 시그니처가 일치함
5. 파일 크기 상한과 보안검사를 통과함

### 7.2. 다운로드하지 않고 링크만 저장하는 경우
- 유료 논문
- 기관인증 또는 로그인 필요
- 자동수집 금지 또는 정책 불명확
- robots/이용정책상 HTML 수집 제한
- 일회성·세션기반 URL만 존재
- 저작권상 기관 내부 자동 보관 여부가 불명확

### 7.3. 우회 금지
다음 기능은 제품 요구사항에서 명시적으로 제외한다.
- CAPTCHA 회피
- 로그인·기관인증 우회
- Paywall 우회
- Anti-bot 방어 회피
- 임시 토큰·세션ID 탈취 또는 재사용
- 금지된 브라우저 자동화 방식으로의 대량 다운로드

---

## 8. 링크·파일 검증 엔진 (Validator)

### 8.1. 1단계 — HTTP/접속 확인
- Redirect 최대 횟수 제한
- 최종 URL 저장
- Status 200 확인
- 403/429는 즉시 우회하지 않고 backoff 후 정책 점검

### 8.2. 2단계 — 자료 일치 확인
- API 제목과 Landing Page 제목 비교
- DOI/공식 ID 비교
- 발행기관·저자·발행일 비교
- PDF 첫 페이지 메타데이터가 추출 가능한 경우 교차검증

### 8.3. 3단계 — 파일 무결성 확인
- `Content-Type`
- PDF magic bytes `%PDF-`
- HWP/HWPX 구조 검사
- 파일 크기 최소/최대값
- HTML 오류페이지가 PDF 확장자로 저장되는 현상 차단

### 8.4. 4단계 — 권리·라이선스 확인
- OA 라이선스 또는 공공누리 등 권리정보 저장
- 불명확하면 `license_unknown=true`
- 라이선스 불명확 자료는 외부 재배포하지 않고 내부 색인·링크 중심으로 처리

---

## 9. 저장 구조 (Storage Architecture)

### 9.1. 기본 원칙
- **수집일자별 목록은 Manifest로 관리**
- **실제 문서는 주제별 폴더에 한 번만 저장**
- 동일 문서를 날짜 폴더와 주제 폴더에 중복 저장하지 않는다.

### 9.2. 권장 폴더 구조

```text
data/
├─ library/
│  ├─ 01_군사법_군사사법/
│  ├─ 02_군인사_복무_징계/
│  ├─ 03_국방정책_행정법/
│  ├─ 04_국방계약_조달법제/
│  ├─ 05_형사_수사_사법/
│  ├─ 06_헌법_인권/
│  ├─ 07_국제법_작전법_국제인도법/
│  ├─ 08_AI_법률AI_디지털법/
│  ├─ 09_법무교육_교육방법론/
│  ├─ 10_비교법_해외법제/
│  ├─ 90_복수주제/
│  └─ 99_미분류_검토필요/
│
├─ manifests/
│  └─ 2026/
│     └─ 08/
│        ├─ 260822.jsonl
│        ├─ 260822.csv
│        └─ 260822.xlsx
│
├─ staging/
│  └─ 260822/
├─ metadata/
├─ summaries/
├─ cache/
├─ quarantine/
└─ logs/
```

### 9.3. 파일명 규칙 — 필수
모든 다운로드 파일명은 **다운로드 받은 연·월·일 6자리(`YYMMDD`)를 맨 앞에 붙인다.**

#### 기본 형식
```text
YYMMDD_[SOURCE]_[짧은제목].[ext]
```

#### 예시
```text
260822_KCI_군사재판절차_개선방안.pdf
260822_SSRN_AI_and_Military_Legal_Education.pdf
260822_NKIS_공공부문_AI_법제연구.pdf
```

#### 세부 규칙
- `YYMMDD`는 **다운로드일** 기준이며 발행일과 별도로 관리
- Windows 예약문자 `\ / : * ? " < > |` 제거
- 연속 공백을 `_`로 변경
- 파일명 전체 길이는 기본 160자 이내 권장
- 동일 파일명 충돌 시 DOI/공식 ID 또는 해시 8자를 추가

```text
260822_KCI_군사재판절차_개선방안__a1b2c3d4.pdf
```

### 9.4. 발행일과 수집일 분리
다음 날짜를 혼용하지 않는다.
- `publication_date`
- `source_registered_date`
- `source_modified_date`
- `discovered_at`
- `downloaded_at`
- `collected_date`

---

## 10. 메타데이터·데이터 모델

### 10.1. Resource 필수 필드
- `resource_id` — 내부 UUID
- `work_id` — 동일 연구성과를 묶는 논리 ID
- `source_id`
- `source_type`
- `title_original`
- `title_ko`
- `authors`
- `publisher`
- `journal_or_series`
- `publication_date`
- `source_registered_date`
- `source_modified_date`
- `discovered_at`
- `downloaded_at`
- `doi`
- `official_identifier`
- `landing_url`
- `download_url`
- `oa_url`
- `license`
- `access_mode`
- `language`
- `document_type`
- `topic_primary`
- `topics`
- `keywords`
- `query_original` — 최초 입력 검색어
- `query_language`
- `query_terms_expanded` — 실제 검색에 사용된 확장 검색어 목록
- `query_dictionary_version`
- `discovered_by_query` — 자료를 실제 발견한 Query
- `abstract_original`
- `file_path`
- `file_sha256`
- `text_sha256`
- `file_size`
- `summary_ko`
- `summary_basis` — `FULLTEXT / ABSTRACT / METADATA_ONLY`
- `relevance_score`
- `priority_level`
- `status`
- `first_seen_at`
- `last_seen_at`
- `alerted_at`

### 10.2. Daily Manifest 필드
- 수집일
- 신규/수정 여부
- 제목
- 출처
- 발행일
- 문서유형
- 주제
- 원문 저장 여부
- 최종 저장 경로
- 링크
- DOI/공식 ID
- 파일 해시
- 중요도
- 요약 상태
- 오류/검토 필요 여부

---

## 11. 중복·개정판·동일 논문 처리 (Deduplication & Versioning)

### 11.1. 중복 판정 우선순위
1. DOI 완전일치
2. arXiv ID/KCI ID/RISS Control No./공식 보고서 ID 등 완전일치
3. 파일 SHA256 일치
4. 정규화 텍스트 SHA256 일치
5. 제목+저자+연도 fuzzy match

### 11.2. 동일 파일의 여러 출처
- 파일은 한 번만 저장
- `resource_source_map` 테이블에 출처별 URL을 모두 보존

### 11.3. 개정판
- 동일 DOI/ID라도 파일 해시가 달라지고 `source_modified_date`가 변경되면 새 버전으로 보존
- 이전 파일 삭제 금지
- `version_of` 관계로 연결

### 11.4. 중복 URL만으로 중복 판단 금지
URL이 달라도 같은 문서일 수 있고, 같은 URL에서 파일이 교체될 수 있으므로 URL 해시만 사용하는 기존 방식은 보조지표로 제한한다.

---

## 12. 주제 분류와 중요도 평가

### 12.1. 하이브리드 분류
1. 규칙 기반 키워드 매칭
2. 제목·초록 임베딩 또는 LLM 분류
3. 기관/학술지 기반 사전분류
4. 낮은 신뢰도는 `99_미분류_검토필요`

### 12.2. 중요도 점수(0~100) 예시
- 주제 적합도: 40
- 출처 신뢰도: 20
- 최신성: 15
- 실무/교육 활용성: 10
- 문서유형 중요도: 10
- OA 및 원문 이용가능성: 5

> 신간 논문은 피인용 횟수가 낮으므로 단순 피인용 수를 핵심 점수로 사용하지 않는다.

### 12.3. 우선순위
- `P1`: 즉시 검토 가치가 높은 핵심 자료
- `P2`: 교육·연구에 유용한 일반 중요 자료
- `P3`: 참고용
- `P4`: 낮은 적합도, 목록만 유지

---

## 13. PDF/HWP/HWPX 처리 및 텍스트 추출

### 13.1. PDF
- 텍스트 레이어가 있는 PDF는 직접 추출
- 페이지 번호를 유지하여 요약 근거를 추적 가능하게 함
- 스캔본은 텍스트 추출 실패 시에만 별도 OCR 후보로 표시

### 13.2. HWP/HWPX
- HWPX는 ZIP/XML 구조 기반 텍스트 추출 우선
- HWP는 라이브러리 호환성 검토 후 추출
- 추출 실패 시 원문은 보존하고 `text_extract_failed=true`

### 13.3. 보안
- 외부에서 받은 파일은 실행하지 않음
- 매크로·실행파일 등 비문서 파일은 `quarantine/`로 이동

---

## 14. 요약·분석 엔진 (Summarization & Research Intelligence)

### 14.1. 요약 단위
신규 문서마다 다음을 생성한다.
1. **한줄 핵심**
2. **핵심 내용 3~5개**
3. **국방·법률 실무상 의미**
4. **군법무 교육에 활용 가능한 포인트**
5. **주요 제한·주의사항**
6. **원문 근거범위**

### 14.2. 요약 근거 수준 표시
- `FULLTEXT`: 원문 전체 또는 주요 본문을 분석
- `ABSTRACT`: 초록만 분석
- `METADATA_ONLY`: 제목·키워드·서지만 분석

알림 화면에서 근거수준을 표시하여 초록 기반 요약을 전체 논문 분석처럼 오인하지 않도록 한다.

### 14.3. 영문 자료
- 영문 제목 원문 보존
- 한국어 번역 제목 별도 생성
- 영문 초록과 한국어 요약을 함께 저장

### 14.4. 법률자료 신뢰성
법령·판례·결정례는 다음을 우선한다.
- 사건번호/법령명/공포·시행일
- 공식 출처 링크
- 개정·변경 여부
- 요약 생성일

LLM이 존재하지 않는 판례·조문·페이지를 생성하지 않도록 원문 기반 검증 단계를 둔다.

---

## 15. 일일 브리핑 및 알림 (Notification)

### 15.1. 기본 채널
- **이메일:** 1순위
- **옵션:** 조직 정책상 허용되는 공식 메시징 API/봇/웹훅 어댑터

### 15.2. 이메일 구성
모바일에서 가로스크롤 없이 읽을 수 있는 카드형 HTML 사용.

#### 헤더
- 수집일
- 신규 자료 수
- 수정 자료 수
- P1/P2 자료 수
- 수집 실패 소스 수

#### 자료별 카드
- 중요도 배지
- 한국어 제목 / 원문 제목
- 출처·저자·발행일
- 주제
- 3줄 요약
- 실무/교육 활용 포인트
- `원문보기` / `저장파일` / `메타데이터` 링크
- 요약 근거수준

### 15.3. 알림 정책
- 기본: `P1 + P2`만 본문 카드로 표시
- P3 이하: 목록 링크 또는 첨부 Excel에 포함
- 오류가 발생한 소스는 별도 경고 섹션 표시

### 15.4. 발송 기술
- Gmail 사용 시 SMTP App Password보다 **Gmail API/OAuth 2.0**을 우선 검토
- API 키·토큰·비밀번호를 소스코드에 저장하지 않음

---

## 16. 스케줄링 (Scheduler)

### 16.1. 일일 작업
- `DAILY_INCREMENTAL`: 매일 1회
- 기본 실행시각은 설정파일에서 지정
- timezone: `Asia/Seoul`

### 16.2. 월간 작업
- `MONTHLY_RECONCILIATION`: 매월 1회
- 최근 30~45일 범위 재검증

### 16.3. 실패 복구
- 소스별 실패가 전체 작업을 중단시키지 않음
- 429/5xx는 exponential backoff
- 연속 실패 횟수가 임계값을 넘으면 해당 소스를 일시 비활성화하고 관리자 알림

### 16.4. 권장 스케줄러
- Windows Task Scheduler
- 또는 APScheduler
- Python `schedule` 단독 사용은 프로세스 종료·재기동·missed job 관리가 약하므로 MVP 이후 비권장

---

## 17. DB·색인·목록 관리

### 17.1. SQLite 기본 테이블
- `sources`
- `works`
- `resources`
- `resource_source_map`
- `files`
- `topics`
- `resource_topics`
- `runs`
- `run_items`
- `alerts`
- `errors`

### 17.2. 검색
- SQLite FTS5를 활용한 제목·초록·요약·추출본문 전문검색
- DOI/기관/저자/기간/주제/출처 필터 지원

### 17.3. CSV/Excel
#### `list_download_resources.csv`
- 전체 누적 메타데이터
- UTF-8-SIG

#### `list_download_resources.xlsx`
- `통합목록`
- `오늘수집`
- `P1_P2`
- `오류_검토필요`
- 월별 시트는 필요 시 자동 생성

> Excel은 편의용 결과물이며 SQLite가 원본(Source of Truth)이다.

---

## 18. 비기능 요구사항 (Non-Functional Requirements)

### 18.1. 안정성
- HTTP timeout 필수
- retry/backoff
- 소스별 circuit breaker
- 실행 중단 후 재개 가능
- staging → validation → atomic move 구조

### 18.2. 예의 있는 수집(Polite Harvesting)
- User-Agent에 서비스명과 관리자 연락처 포함 가능
- API 권장 호출량 준수
- 소스별 concurrency 제한
- Cache-Control/ETag/Last-Modified 활용

### 18.3. 보안
- `.env` 또는 OS Secret Store 사용
- API Key/Gmail Token을 Git에 커밋 금지
- 로그에서 인증값 마스킹
- 파일 업로드·실행 기능 분리

### 18.4. 감사가능성(Auditability)
각 자료에 대해 다음을 역추적할 수 있어야 한다.
- 언제 발견했는가
- 어떤 API/URL에서 발견했는가
- 어떤 정책으로 다운로드했는가
- 원문 해시는 무엇인가
- 어떤 버전인가
- 어떤 근거로 주제/중요도가 정해졌는가
- 언제 어떤 요약이 생성되었는가

### 18.5. 저작권·이용조건
- 메타데이터와 원문 이용권한을 분리하여 기록
- 내부 교육용 저장과 외부 재배포 가능 여부를 분리
- 원문을 이메일 첨부로 재배포하지 않고 기본적으로 공식 링크를 제공

---

## 19. 기술 스택 (Recommended Tech Stack)

### 19.1. Core
- **Python:** 3.11+
- **HTTP:** `httpx` 또는 `requests`
- **Parsing:** `beautifulsoup4`, `lxml`
- **Feed:** `feedparser`
- **OAI-PMH:** `sickle` 또는 직접 OAI-PMH client
- **Data validation:** `pydantic`
- **Retry:** `tenacity`
- **Config:** `pyyaml`, `python-dotenv`
- **Database:** SQLite3 + FTS5, 필요 시 SQLAlchemy
- **Excel:** `openpyxl`, `pandas`
- **PDF:** `PyMuPDF` 또는 `pypdf`
- **Filename safety:** `pathvalidate`
- **Scheduler:** APScheduler / Windows Task Scheduler
- **Logging:** 표준 `logging` + rotating file handler

### 19.2. 선택사항
- 임베딩 기반 주제분류: `sentence-transformers`
- 로컬 벡터검색: FAISS/Chroma 등
- LLM 요약: 공급자 교체 가능한 adapter 구조

### 19.3. 제거 또는 변경 권고
- `deep-translator`: 핵심 의존성에서 제외하고 선택 기능으로 전환
- Python `schedule`: 단독 운영 대신 APScheduler 또는 OS Scheduler 우선
- DuckDuckGo HTML 검색 스크래핑: 핵심 수집방식에서 제거

---

## 20. 프로젝트 구조 예시

```text
project/
├─ config/
│  ├─ sources.yaml
│  ├─ topics.yaml
│  ├─ search_terms.yaml
│  └─ config.yaml
├─ src/
│  ├─ connectors/
│  │  ├─ base.py
│  │  ├─ kci.py
│  │  ├─ riss.py
│  │  ├─ nkis.py
│  │  ├─ law_openapi.py
│  │  ├─ crossref.py
│  │  ├─ openalex.py
│  │  ├─ semantic_scholar.py
│  │  ├─ core.py
│  │  ├─ unpaywall.py
│  │  ├─ doaj.py
│  │  ├─ arxiv.py
│  │  └─ ssrn.py
│  ├─ discovery/
│  ├─ downloader/
│  ├─ validators/
│  ├─ normalizers/
│  ├─ dedup/
│  ├─ classifier/
│  ├─ summarizer/
│  ├─ storage/
│  ├─ notifier/
│  ├─ database/
│  └─ scheduler/
├─ data/
├─ logs/
├─ tests/
├─ scripts/
├─ docs/
│  ├─ API_발급_연동_가이드.md
│  └─ 운영자_매뉴얼.md
├─ .env.example
├─ requirements.txt
└─ README.md
```

---

## 21. Source Adapter 표준 인터페이스

각 수집기는 최소 다음 함수를 구현한다.

```python
class SourceConnector:
    def prepare_queries(self, terms, source_language): ...
    def discover(self, since, until, queries): ...
    def fetch_metadata(self, item): ...
    def normalize(self, raw): ...
    def resolve_download(self, metadata): ...
    def check_access_policy(self, candidate): ...
    def download(self, candidate): ...
```

소스별 구현 차이를 core pipeline과 분리하여 사이트 구조 변경 시 해당 Adapter만 수정할 수 있도록 한다.

---

## 22. 오류·예외 처리

### 오류 코드 예시
- `DISCOVERY_FAILED`
- `API_RATE_LIMIT`
- `POLICY_BLOCKED`
- `LOGIN_REQUIRED`
- `PAYWALL`
- `LINK_EXPIRED`
- `FILE_NOT_DOCUMENT`
- `FILE_CORRUPTED`
- `DUPLICATE_FILE`
- `TEXT_EXTRACTION_FAILED`
- `SUMMARY_FAILED`

### 원칙
- 실패한 자료는 삭제하지 않고 상태와 원인을 DB에 기록
- 링크만 확보한 자료도 리서치 가치가 있으므로 `LINK_ONLY`로 보존

---

## 23. 품질 지표 및 수용기준 (Acceptance Criteria)

### 23.1. MVP 필수
- [ ] KCI Open API/OAI-PMH 수집 가능
- [ ] 국내 검색어 사전에 포렌식, 위법수집증거, 판결, 방위사업법, 군사기밀보호법, 군사기지, 사법제도, 군검찰, 군사경찰, 증거능력, 법률전, 군검사, 형사소송법, 군사법원, 통합방위법이 포함됨
- [ ] `query_language=en` 소스에서 한국어 seed term을 검수된 영문 학술용어로 변환·확장하여 검색 가능
- [ ] 검색에 실제 사용된 번역·확장 Query와 사전 버전을 DB/Manifest에 기록
- [ ] NKIS Open API 수집 가능
- [ ] 디지털집현전 Open API 수집 가능 *(2026-08-23 추가)*
- [ ] 국가법령정보 공동활용 Open API 수집 가능
- [ ] Crossref/OpenAlex/Unpaywall 중 최소 2개 연동
- [ ] SSRN 논문을 외부 학술 메타데이터를 통해 발견하고 공식 SSRN Landing Page 연결 가능
- [ ] RISS는 Open API 승인 여부에 따라 API/Link-only로 동작 가능
- [ ] `YYMMDD_` 접두사 파일명 규칙 100% 적용
- [ ] 일자별 Manifest와 주제별 최종저장 구조 동시 구현
- [ ] DOI/파일 해시 기반 중복차단
- [ ] 매일 신규자료 요약 이메일 발송
- [ ] 출처·원문·라이선스·요약근거 추적 가능
- [ ] 인증이 필요한 모든 Connector에 대해 `docs/API_발급_연동_가이드.md` 생성 및 공식문서 확인일 기록
- [ ] API 가이드와 `.env.example`에 실제 비밀키/토큰이 포함되지 않음

### 23.2. 품질 목표
- 다운로드 성공한 파일의 문서 무결성 검사 성공률 99% 이상
- 동일 binary 파일 중복 저장률 1% 미만
- DOI 보유 자료의 DOI 저장률 98% 이상
- `P1/P2` 자료의 잘못된 주제분류율 5% 이하를 목표로 샘플 검수
- API 정책상 금지된 다운로드 시도 0건

---

## 24. 구현 단계 (Roadmap)

### Phase 0 — 검색어·인증 준비
- 국내 필수 검색어 `search_terms.yaml` 구축
- 영문 법률·국제법 용어 대응사전 구축 및 샘플 검수
- Source별 인증방식 조사
- `docs/API_발급_연동_가이드.md` 초안 작성
- `.env.example` 정의

### Phase 1 — 국내 공공·법률 MVP
- Source Registry
- KCI
- NKIS
- 국가법령정보 공동활용
- 기관형 공공자료 3~5개
- SQLite/Manifest/주제별 저장
- Gmail 일일 브리핑

### Phase 2 — 국제 학술 확장
- Crossref
- OpenAlex
- Unpaywall
- CORE
- Semantic Scholar
- arXiv
- DOAJ
- SSRN discovery/landing 연계

### Phase 3 — RISS·ScienceON·AccessON 및 기관별 Adapter 고도화
- RISS Open API 승인 가능성 확인 및 연동
- ScienceON API
- OA 대체본 자동 탐색
- 국내 학술 중복 통합

### Phase 4 — 요약·교육 인텔리전스
- 중요도 자동점수
- 법무교육 활용 포인트
- 주간/월간 트렌드
- 주제별 누적 리서치 브리프

### Phase 5 — 운영·감사·모니터링
- 대시보드
- 정책 변경 감시
- 소스별 장애율/누락률
- 백업·복구
- 운영자 매뉴얼

---

## 25. 최종 설계 원칙 요약

1. **크롤링 프로그램이 아니라 “Source Adapter 기반 연구정보 수집 플랫폼”으로 설계한다.**
2. **API/OAI-PMH/RSS가 있으면 HTML 크롤링보다 반드시 우선한다.**
3. **SSRN·RISS는 중요하지만 접근정책과 원문 권리를 무시한 대량 다운로드 방식은 사용하지 않는다.**
4. **원문이 제한되면 DOI·초록·공식 Landing Page만으로도 자료를 잃지 않도록 한다.**
5. **OA 원문은 Unpaywall·CORE·OpenAlex·KCI·ScienceON·AccessON 등을 교차 조회하여 합법적 공개본을 최대한 찾는다.**
6. **다운로드 파일은 반드시 `260822_`와 같은 `YYMMDD_` 접두사를 사용한다.**
7. **일자별 이력은 Manifest, 실제 파일은 주제별 저장소에 보관하여 중복을 방지한다.**
8. **발행일·등록일·수정일·수집일을 분리하여 최신성 판단 오류를 줄인다.**
9. **URL이 아니라 DOI/공식 ID/파일 해시를 중심으로 중복과 버전을 관리한다.**
10. **일일 수집 → 검증 → 분류 → 저장 → 요약 → 알림까지 하나의 재현 가능한 파이프라인으로 운영한다.**
11. **영문 학술소스는 한국어 검색어를 그대로 사용하는 대신 검수된 한·영 전문용어 사전으로 변환·확장한다.**
12. **국내 검색어는 별도 사전파일로 관리하고 필수 군사법·형사법·방산법 키워드의 누락을 자동검사한다.**
13. **API Key/OAuth/기관승인이 필요한 연결은 구현 시 공식 문서를 다시 확인하고 별도 발급·연동 가이드를 반드시 제공한다.**


---

## 26. v2.1 변경 이력 (2026-08-22)
- 영문 학술DB용 **한글→영문 전문용어 변환·동의어 확장 엔진** 요구사항 추가
- `config/search_terms.yaml` 및 검색어 사전 버전관리 추가
- 국내 학술검색 필수 키워드 세트 추가
- 검색에 사용한 원문/확장 Query 및 사전 버전을 Resource/Manifest에 기록하도록 데이터모델 확장
- Source Registry의 단순 `api_key_required` 필드를 **접근방식별 인증모델**로 개편
- 구현 시 `docs/API_발급_연동_가이드.md`를 별도 산출물로 생성하도록 필수 요구사항 추가
- KCI처럼 접근방식별 인증 요구가 다른 경우를 지원하도록 설계 보완
- OpenAlex 등 인증·쿼터 정책이 변할 수 있는 서비스는 구현 직전 공식문서 재검증을 수용기준에 반영
