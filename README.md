# DL-RCIS — 국방·법률·공공·학술 리서치 자동수집·요약·알림 시스템

> **Defense & Legal Research Collection and Intelligence System**
> 사양서: [PRD.md](PRD.md) (v2.1, 2026-08-22)

정부기관·사법기관·연구기관·학술단체·오픈액세스 저장소의 공개 전문자료를
**공식 API / OAI-PMH / RSS 를 통해** 매일 자동으로 탐색·수집하고,
주제별로 분류·보관한 뒤 한국어 요약과 함께 일일 브리핑을 발송합니다.

---

## 핵심 설계 원칙

```
공식 API/OAI-PMH/RSS 우선 → 허용된 공개 웹 접근 → 링크 보존
```

1. **크롤러가 아니라 Source Adapter 기반 수집 플랫폼입니다.**
   검색엔진 HTML 결과를 스크래핑하지 않습니다.
2. **로그인·유료결제·CAPTCHA·접근통제·자동화 금지 정책을 우회하지 않습니다.**
3. **원문을 받을 수 없어도 자료를 잃지 않습니다.** DOI·초록·공식 Landing Page 를 보존합니다.
4. **URL 이 아니라 DOI/공식 ID/파일 해시**로 중복과 버전을 관리합니다.
5. **발행일·등록일·수정일·수집일을 분리**해 최신성 판단 오류를 줄입니다.

---

## 주요 기능

| 기능 | 설명 | PRD |
| --- | --- | --- |
| 일일 증분 수집 | 매일 지정 시각(KST)에 신규·수정 자료 조회, 최근 3일 look-back | §UC-02 |
| 월간 정합성 점검 | 매월 1회 최근 45일 재조회로 지연 등록·수정본·누락 보정 | §UC-03 |
| 다국어 검색어 확장 | 한국어 seed term 을 **검수된 영문 학술용어**로 변환·확장해 영문 DB 검색 | §6.4 |
| 3단계 링크 검증 | 접속 확인 → 자료 일치 확인 → 파일 무결성 → 권리 확인 | §8 |
| OA 원문 탐색 | Unpaywall·CORE·ScienceON 교차 조회로 합법적 공개본 확보 | §6.1-7 |
| 주제별 지식저장소 | 파일은 주제 폴더에 **한 번만** 저장, 일자 이력은 Manifest 로 관리 | §9 |
| 다단계 중복 제거 | DOI → 공식 ID → 파일 SHA256 → 텍스트 SHA256 → 제목 fuzzy | §11 |
| 요약·중요도 분석 | 한국어 요약 + 교육 활용 포인트 + **요약 근거수준** 표기 | §14 |
| 일일 브리핑 | 모바일 카드형 HTML 메일, P1·P2 는 카드 / P3 이하는 목록 | §15 |

---

## 프로젝트 구조

```text
Collecting_resources/
├─ config/
│  ├─ config.yaml            # 운영 설정 (스케줄, 임계값, 저장 경로)
│  ├─ sources.yaml           # Source Registry — 모든 출처와 접근정책
│  ├─ topics.yaml            # 주제 분류 체계 (12개)
│  └─ search_terms.yaml      # 검색어 사전 (한·영 대응, 버전관리)
├─ src/
│  ├─ connectors/            # Source Adapter (§21 표준 인터페이스)
│  │  ├─ base.py             #   공통 인터페이스 + 접근정책 판정
│  │  ├─ kci.py riss.py nkis.py prism.py scienceon.py law_openapi.py
│  │  ├─ crossref.py openalex.py semantic_scholar.py core.py
│  │  ├─ unpaywall.py doaj.py arxiv.py ssrn.py zenodo.py
│  │  ├─ institution_feed.py #   기관 RSS/Atom
│  │  ├─ generic_api.py      #   설정 주도형 Open API 어댑터
│  │  └─ oai_pmh.py          #   OAI-PMH 하베스터
│  ├─ discovery/             # 검색어 확장 + 파이프라인 오케스트레이션
│  ├─ downloader/            # 다운로더 + OA Resolver
│  ├─ validators/            # 링크·파일·라이선스 검증
│  ├─ normalizers/           # DOI·날짜·제목 정규화
│  ├─ dedup/                 # 중복·개정판 판별
│  ├─ classifier/            # 주제 분류 + 중요도 산정
│  ├─ summarizer/            # 추출식(기본) / LLM(선택) 요약
│  ├─ storage/               # 주제별 저장소 + Manifest + CSV/Excel
│  ├─ notifier/              # 카드형 HTML 이메일
│  ├─ database/              # SQLite + FTS5 (Source of Truth)
│  ├─ extractors/            # PDF/HWP/HWPX 텍스트 추출
│  └─ scheduler/             # APScheduler 기반 일일/월간 예약
├─ data/
│  ├─ library/               # 주제별 최종 보관 (실제 파일)
│  │  ├─ 01_군사법_군사사법/ … 99_미분류_검토필요/
│  ├─ manifests/YYYY/MM/     # 일자별 수집 목록 (jsonl/csv/xlsx)
│  ├─ staging/               # 검증 전 임시 다운로드
│  ├─ metadata/              # SQLite DB, 누적 CSV/Excel
│  └─ quarantine/            # 비문서·실행파일 격리
├─ docs/
│  ├─ API_발급_연동_가이드.md  # 자동 생성 — 인증정보 발급 절차
│  └─ 운영자_매뉴얼.md
├─ scripts/
│  ├─ setup_scheduler.bat    # Windows 작업 스케줄러 등록
│  ├─ generate_api_guide.py  # API 가이드 생성기
│  └─ check_search_terms.py  # 검색어 사전 품질 점검
├─ tests/
├─ main.py                   # CLI 진입점
├─ requirements.txt
└─ .env.example              # 환경변수 템플릿 (실제 값 없음)
```

---

## 설치

```bash
# 1) 의존성 설치
pip install -r requirements.txt

# 2) 환경변수 템플릿 복사
cp .env.example .env        # Windows: copy .env.example .env

# 3) 설정 점검
python main.py doctor
```

**Python 3.11 이상**이 필요합니다.

---

## 설정

### 1. 인증정보 (`.env`)

`.env` 에 실제 값을 채웁니다. **이 파일은 절대 Git 에 커밋하지 마십시오.**

```bash
CONTACT_EMAIL=your.name@example.org     # Crossref polite pool, Unpaywall 필수 파라미터
DLRCIS_SENDER_EMAIL=sender@gmail.com
DLRCIS_RECEIVER_EMAIL=you@gmail.com
DLRCIS_SMTP_PASSWORD=                   # Gmail 앱 비밀번호
OPENALEX_API_KEY=                       # 2026-02-13 부터 필수
KCI_API_KEY=
NKIS_API_KEY=
LAW_GO_KR_OC=
```

각 값의 **발급 절차는 [docs/API_발급_연동_가이드.md](docs/API_발급_연동_가이드.md)** 에 소스별로 정리되어 있습니다.
이 문서는 `config/sources.yaml` 에서 자동 생성됩니다:

```bash
python main.py api-guide --excel
```

> 인증정보가 없거나 엔드포인트가 확정되지 않은 소스는 **자동으로 건너뛰고** 나머지 소스로 계속 진행합니다.
>
> **별도 발급 없이 바로 쓸 수 있는 소스**: Crossref, arXiv, DOAJ, Zenodo, Semantic Scholar, KCI(OAI-PMH)
>
> **주의**: OpenAlex 는 2026-02-13 부터 API Key 가 필수가 되었고 polite pool(mailto)이 폐지되었습니다.
> 키 없이 호출하면 시험용 크레딧 소진 후 409 를 반환하므로 `OPENALEX_API_KEY` 를 발급받아야 합니다.

### 2. 수집 대상 (`config/sources.yaml`)

각 접근방식에는 **확인 근거**가 함께 기록됩니다 (§18.4 감사가능성).

| 필드 | 의미 |
| --- | --- |
| `verification_status` | `VERIFIED` = 공식 문서로 확정 / `PENDING_VERIFICATION` = 미확정 |
| `verified_source` | 확인 근거가 된 공식 문서 URL |
| `verified_at` | 확인 일자 |
| `verified_method` | `official_doc`(직접 열람) / `web_search`(공식 문서 검색결과) |

확인되지 않은 항목의 `endpoint` 는 **비워 둡니다.** URL 을 추측해 채우지 않으며,
비어 있으면 해당 소스의 자동수집을 시도하지 않고 건너뜁니다.

새 소스를 추가하거나 접근정책을 바꿀 때 이 파일만 수정합니다.
엔드포인트가 비어 있으면 자동수집을 시도하지 않습니다.

```yaml
- source_id: nkis
  name: "NKIS 국가정책연구포털"
  connector: nkis
  mode: [FULL, QUERY]
  access_methods:
    - type: OPEN_API
      auth_type: API_KEY
      credential_required: true
      credential_env_var: NKIS_API_KEY   # 변수명만! 실제 키는 .env 에
      endpoint: ""                        # 공식 문서 확인 후 입력
  download_policy: allowed                # allowed | oa_only | link_only | manual_review
  rate_limit_rps: 0.5
```

### 3. 검색어 (`config/search_terms.yaml`)

PRD §3.3 이 요구하는 21개 필수 키워드가 등록되어 있습니다.
영문 소스에는 한국어를 그대로 보내지 않고 `en_terms` 로 변환·확장해 검색합니다.

```yaml
- canonical_ko: 작전법
  ko_variants: ["작전 법"]
  en_terms: ["operational law"]
  topic_id: "07_국제법_작전법_국제인도법"
  human_verified: true
```

```bash
python scripts/check_search_terms.py   # 필수 키워드 누락·영문 대응어 점검
```

---

## 실행

```bash
# 일일 증분 수집 (전일 이후 신규·수정 자료)
python main.py run --daily

# 초기 백필 (config 의 backfill_start_date ~ 오늘)
python main.py run --backfill

# 월간 정합성 점검 (최근 45일 재조회)
python main.py run --reconcile

# 특정 소스만 / 기간 지정 / 저장 없이 탐색만
python main.py run --source kci arxiv --since 2026-08-01 --dry-run

# 스케줄러 데몬 (매일 07:30, 매월 1일 05:00 · KST)
python main.py schedule

# 설정·인증정보·저장소 점검
python main.py doctor

# 수집 자료 전문검색 (SQLite FTS5)
python main.py search "군사법원 증거능력"

# CSV/Excel 재생성
python main.py export
```

### Windows 작업 스케줄러 등록 (권장)

`scripts/setup_scheduler.bat` 를 **관리자 권한으로 실행**하면
매일 07:30 증분 수집과 매월 1일 05:00 정합성 점검이 등록됩니다.

---

## 결과물

### 1. 주제별 지식저장소

파일은 주제 폴더에 **한 번만** 저장되며, 파일명은 **다운로드일 `YYMMDD`** 로 시작합니다.

```text
data/library/01_군사법_군사사법/260822_KCI_군사재판절차_개선방안.pdf
data/library/07_국제법_작전법_국제인도법/260822_SSRN_Operational_Law_Review.pdf
```

### 2. 일자별 Manifest

그날 무엇을 수집했는지는 Manifest 가 기록합니다 (파일 중복 저장 없음).

```text
data/manifests/2026/08/260822.jsonl   # 전체 필드 (감사 추적용)
data/manifests/2026/08/260822.csv     # 요약 목록
data/manifests/2026/08/260822.xlsx
```

### 3. 누적 목록

- `data/metadata/list_download_resources.csv` (UTF-8-SIG)
- `data/metadata/list_download_resources.xlsx`
  — `통합목록` / `오늘수집` / `P1_P2` / `오류_검토필요` / 월별 시트

> Excel 은 편의용이며 **SQLite(`data/metadata/dlrcis.db`)가 원본(Source of Truth)** 입니다.

### 4. 일일 브리핑 메일

모바일에서 가로스크롤 없이 읽히는 카드형 HTML.
각 카드에 중요도 배지·주제·3줄 요약·교육 활용 포인트·**요약 근거수준**이 표시됩니다.

| 근거수준 | 의미 |
| --- | --- |
| `FULLTEXT` | 원문 전체 분석 |
| `ABSTRACT` | 초록만 분석 |
| `METADATA_ONLY` | 제목·키워드·서지만 분석 |

P1·P2 는 본문 카드, P3 이하는 목록 링크와 첨부 Excel 로 제공합니다.
**원문 파일은 첨부하지 않고 공식 링크를 제공합니다.**

---

## 접근정책 요약

| 상황 | 동작 |
| --- | --- |
| 공식 API·OA 라이선스 확인 | 원문 자동 다운로드 |
| 라이선스 불명확 | `LINK_ONLY` — 메타데이터·링크만 보존, 외부 재배포 금지 |
| 로그인·결제·CAPTCHA 필요 | 다운로드하지 않고 사유를 기록 |
| RISS | 공개 API 는 상호대차·E-DDS·통계·FRIC 용이며 학술 서지 검색 API 가 없어 Landing Page 만 보존 |
| SSRN | 외부 학술 메타데이터로 발견 → 공식 Abstract Page 연결 (자동 다운로드 없음) |
| robots.txt 금지 경로 | 요청하지 않음 |
| 403 / 429 | 즉시 우회하지 않고 backoff 후 정책 재점검, 연속 실패 시 소스 일시 비활성화 |

---

## 요약 공급자 전환

기본은 외부 API가 필요 없는 **추출식 요약**입니다.
LLM 요약을 쓰려면 `config/config.yaml` 을 수정하고 `.env` 에 키를 넣습니다.

```yaml
summarizer:
  provider: "llm"          # extractive | llm
  llm:
    model: "claude-opus-5"
    effort: "medium"
```

키가 없거나 호출에 실패하면 자동으로 추출식 요약으로 대체되며, 수집은 중단되지 않습니다.
원문을 외부로 전송하게 되므로 **조직 정책을 먼저 확인**하십시오.

---

## 테스트

```bash
python -m pytest tests/ -q
```

`tests/test_acceptance.py` 는 PRD §23.1 MVP 수용기준을 항목별로 검증합니다.

---

## 문서

- [PRD.md](PRD.md) — 제품 요구사항 정의서 v2.1
- [docs/API_발급_연동_가이드.md](docs/API_발급_연동_가이드.md) — 소스별 인증정보 발급 절차
- [docs/운영자_매뉴얼.md](docs/운영자_매뉴얼.md) — 일상 운영·장애 대응
