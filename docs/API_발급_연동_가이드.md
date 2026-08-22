# API 발급·연동 가이드

> 이 문서는 `config/sources.yaml` 에서 **자동 생성**됩니다.
> 수정하려면 `config/sources.yaml` 을 고친 뒤 `python main.py api-guide` 를 다시 실행하십시오.
>
> - 생성일: 2026-08-22
> - Source Registry 버전: `2026.08.22-1`
> - 대상 소스: 전체 21개 (사전 발급·승인 필요 10개)

## 0. 읽기 전 안내

이 가이드는 **비개발자도 인증정보를 직접 발급받아 시스템에 연결할 수 있도록** 작성되었습니다.

### 보안 원칙 (PRD §5.1)

1. 실제 API Key, Client Secret, Refresh Token 을 **이 문서에 기록하지 마십시오.**
2. 이 문서에는 **환경변수명만** 적습니다. 예: `KCI_API_KEY`
3. 실제 값은 프로젝트 루트의 `.env` (Git 제외) 또는 OS Secret Store 에 저장합니다.
4. `.env.example` 에는 변수명과 설명만 넣고 실제 값은 넣지 않습니다.

### 최신성 원칙

API 발급·인증 방식은 변경될 수 있습니다. **Connector 를 실제로 연결하기 직전에 공식 문서를 다시 확인**하십시오.
블로그·카페·개인 튜토리얼은 보조자료로만 사용하고, 발급절차·쿼터·가격·권한은 공식 문서를 기준으로 판단합니다.

`확인상태: PENDING_VERIFICATION` 으로 표시된 항목은 아직 공식 문서로 확정되지 않은 부분이며,
**엔드포인트가 비어 있으면 시스템은 해당 소스의 자동수집을 시도하지 않고 건너뜁니다.**

### 발급 절차 요약

```
1) 아래 표에서 필요한 소스를 고른다
2) '공식 발급/신청 페이지' 로 이동해 계정을 만들고 활용 신청을 한다
3) 발급받은 값을 프로젝트 루트 .env 파일에 '환경변수명=값' 형태로 적는다
4) 필요하면 config/sources.yaml 의 endpoint 를 공식 문서 기준으로 채운다
5) python main.py doctor 로 인식 여부를 확인한다
```

## 1. 인증정보가 필요한 소스 요약

| 소스 | 인증방식 | 환경변수 | 승인 필요 | 확인상태 |
| --- | --- | --- | --- | --- |
| KCI 한국학술지인용색인 (`kci`) | OPEN_API / API Key 필요 | `KCI_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |
| RISS 학술연구정보서비스 (`riss`) | OPEN_API / 기관 승인 필요 | `RISS_API_KEY` | 예 | `PENDING_VERIFICATION` |
| ScienceON (KISTI) (`scienceon`) | OPEN_API / API Key 필요 | `SCIENCEON_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |
| NKIS 국가정책연구포털 (`nkis`) | OPEN_API / API Key 필요 | `NKIS_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |
| PRISM 정책연구관리시스템 (`prism`) | OPEN_API / API Key 필요 | `DATA_GO_KR_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |
| 국가법령정보 공동활용 (`law_go_kr`) | OPEN_API / API Key 필요 | `LAW_GO_KR_OC` | 신청 필요 | `PENDING_VERIFICATION` |
| Semantic Scholar (`semantic_scholar`) | OPEN_API / API Key 필요 | `SEMANTIC_SCHOLAR_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |
| CORE (`core`) | OPEN_API / API Key 필요 | `CORE_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |
| Unpaywall (`unpaywall`) | OPEN_API / 불필요 | `CONTACT_EMAIL` | 신청 필요 | `VERIFIED` |
| Zenodo (`zenodo`) | OPEN_API / API Key 필요 | `ZENODO_API_KEY` | 신청 필요 | `PENDING_VERIFICATION` |

## 2. 별도 발급 없이 사용 가능한 소스

- **국회입법조사처** (`nars`) — 별도 발급 없이 사용 가능
- **사법정책연구원** (`jpri`) — 별도 발급 없이 사용 가능
- **법무연수원** (`ioj`) — 별도 발급 없이 사용 가능
- **한국형사·법무정책연구원** (`kicj`) — 별도 발급 없이 사용 가능
- **국가인권위원회** (`humanrights`) — 별도 발급 없이 사용 가능
- **한국국방연구원 (KIDA)** (`kida`) — 별도 발급 없이 사용 가능
- **Crossref** (`crossref`) — 별도 발급 없이 사용 가능 (연락 이메일 `CONTACT_EMAIL` 권장)
- **OpenAlex** (`openalex`) — 별도 발급 없이 사용 가능 (연락 이메일 `CONTACT_EMAIL` 권장)
- **DOAJ** (`doaj`) — 별도 발급 없이 사용 가능
- **arXiv** (`arxiv`) — 별도 발급 없이 사용 가능
- **SSRN** (`ssrn`) — 별도 발급 없이 사용 가능

> Crossref·OpenAlex 는 연락 이메일을 제공하면 polite pool 로 안정적인 응답을 받습니다.
> Unpaywall 은 모든 요청에 이메일이 **필수**입니다.

## 3. 소스별 상세 발급 절차

### KCI 한국학술지인용색인 (`kci`)

- **OAI_PMH** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `KCI_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | KCI 한국학술지인용색인 |
| 2. 사용 API/인증방식 | OAI_PMH(불필요), OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://open.kci.go.kr |
| 5. 계정 생성 필요 여부 | 예 (KCI 회원가입) |
| 6. 신청 메뉴 경로 | KCI 오픈 서비스 → Open API 신청 메뉴에서 이용 신청 |
| 7. 서비스 목적 예시 | 군사법·형사법 분야 국내 학술논문 메타데이터의 정기 수집 및 사내 리서치 색인 구축 |
| 8. 승인 절차 | 신청 후 운영기관 검토 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 (API Key 방식) |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `KCI_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source kci --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | OAI-PMH 는 별도 인증 없이 사용할 수 있는지 독립적으로 확인하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://open.kci.go.kr/po/openapi/oai`
  - `https://open.kci.go.kr/po/openapi/openApiSearch.kci`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OAI_PMH, OPEN_API

---

### RISS 학술연구정보서비스 (`riss`)

- **OPEN_API** — 인증: 기관 승인 필요 / 사전 발급 필요: 예 / 환경변수: `RISS_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | RISS 학술연구정보서비스 |
| 2. 사용 API/인증방식 | OPEN_API(기관 승인 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.riss.kr |
| 5. 계정 생성 필요 여부 | 예 |
| 6. 신청 메뉴 경로 | RISS 고객센터/제휴 문의를 통해 Open API 활용 신청 |
| 7. 서비스 목적 예시 | 국방·법률 주제 학술자료의 서지 메타데이터 수집 (원문 자동 다운로드 없음) |
| 8. 승인 절차 | 기관 검토·승인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `RISS_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source riss --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 승인 전에는 직접 크롤링하지 말고 LINK_ONLY 로 유지하십시오. 화면상 '원문있음' 표시가 자동 다운로드 권한을 의미하지 않습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 0.2`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### ScienceON (KISTI) (`scienceon`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `SCIENCEON_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | ScienceON (KISTI) |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://scienceon.kisti.re.kr |
| 5. 계정 생성 필요 여부 | 예 (KISTI 통합회원) |
| 6. 신청 메뉴 경로 | ScienceON → API 서비스 → 활용 신청 |
| 7. 서비스 목적 예시 | 국내외 학술논문·연구보고서 메타데이터 및 오픈액세스 원문 위치 탐색 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | API 별 이용조건 확인 필요 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `SCIENCEON_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source scienceon --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | AccessON 오픈액세스 검색은 별도 이용조건이 적용될 수 있습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://apigateway.kisti.re.kr/openapicall.do`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### NKIS 국가정책연구포털 (`nkis`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `NKIS_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | NKIS 국가정책연구포털 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.nkis.re.kr |
| 5. 계정 생성 필요 여부 | 예 |
| 6. 신청 메뉴 경로 | NKIS 회원가입 → Open API 활용신청 → 기관검토 → 인증키 발급 |
| 7. 서비스 목적 예시 | 정부출연연구기관 연구보고서의 정기 수집 및 내부 리서치 아카이브 구축 |
| 8. 승인 절차 | 기관 검토 후 승인 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `NKIS_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source nkis --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 발급받은 엔드포인트를 config/sources.yaml 의 endpoint 에 입력해야 동작합니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: allowed` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### PRISM 정책연구관리시스템 (`prism`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `DATA_GO_KR_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | PRISM 정책연구관리시스템 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.data.go.kr |
| 5. 계정 생성 필요 여부 | 예 (공공데이터포털 회원가입) |
| 6. 신청 메뉴 경로 | 공공데이터포털 → 해당 오픈API 검색 → 활용신청 |
| 7. 서비스 목적 예시 | 중앙·지방정부 정책연구용역 보고서의 정기 수집 |
| 8. 승인 절차 | 자동승인 또는 기관 검토 (API 별 상이) |
| 9. 무료/유료 및 쿼터 | 공공데이터포털 기준 무료(트래픽 한도 있음) |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `DATA_GO_KR_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source prism --dry-run` |
| 14. 키 만료·갱신·회수 | 공공데이터포털 마이페이지에서 활용기간 연장 신청 |
| 15. 이용약관·자동수집 주의사항 | 일반 인증키(Encoding/Decoding) 구분에 주의하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: allowed` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### 국가법령정보 공동활용 (`law_go_kr`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `LAW_GO_KR_OC` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국가법령정보 공동활용 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://open.law.go.kr |
| 5. 계정 생성 필요 여부 | 예 |
| 6. 신청 메뉴 경로 | 국가법령정보 공동활용 → 오픈API 신청 |
| 7. 서비스 목적 예시 | 군사법·국방 관련 법령·행정규칙·판례의 신규 제정 및 개정 추적 |
| 8. 승인 절차 | 신청 후 승인 (승인 시 OC 식별자 부여) |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `LAW_GO_KR_OC` |
| 13. 동작 확인 방법 | `python main.py run --daily --source law_go_kr --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | OC 는 API Key 가 아니라 사용자 식별자이지만 동일하게 .env 로 관리합니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://www.law.go.kr/DRF/lawSearch.do`

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 1.0`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### 국회입법조사처 (`nars`)

- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국회입법조사처 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://www.nars.go.kr |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 RSS 주소 확인 후 endpoint 를 채우면 자동 활성화됩니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 사법정책연구원 (`jpri`)

- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 사법정책연구원 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://jpri.scourt.go.kr |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 문서 확인 필요 |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 법무연수원 (`ioj`)

- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 법무연수원 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://www.ioj.go.kr |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 문서 확인 필요 |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 한국형사·법무정책연구원 (`kicj`)

- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 한국형사·법무정책연구원 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://www.kicj.re.kr |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 문서 확인 필요 |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 국가인권위원회 (`humanrights`)

- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국가인권위원회 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://www.humanrights.go.kr |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 문서 확인 필요 |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 한국국방연구원 (KIDA) (`kida`)

- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 한국국방연구원 (KIDA) |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://www.kida.re.kr |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 문서 확인 필요 |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### Crossref (`crossref`)

- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: `CONTACT_EMAIL` / 확인상태: `VERIFIED`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | Crossref |
| 2. 사용 API/인증방식 | OPEN_API(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://api.crossref.org/swagger-ui/index.html |
| 5. 계정 생성 필요 여부 | 아니오 |
| 6. 신청 메뉴 경로 | 별도 신청 없이 사용 가능. 연락 이메일(mailto)을 제공하면 polite pool 을 사용합니다. |
| 7. 서비스 목적 예시 | DOI 메타데이터 정규화 및 중복 판별 (연구 목적) |
| 8. 승인 절차 | 불필요 |
| 9. 무료/유료 및 쿼터 | 무료 (Plus 서비스는 유료) |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `CONTACT_EMAIL` |
| 13. 동작 확인 방법 | `python main.py run --daily --source crossref --dry-run` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | CONTACT_EMAIL 을 설정하지 않으면 공유 풀에서 속도가 제한될 수 있습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.crossref.org/works`

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 1.0`

---

### OpenAlex (`openalex`)

- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: `CONTACT_EMAIL` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | OpenAlex |
| 2. 사용 API/인증방식 | OPEN_API(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://docs.openalex.org |
| 5. 계정 생성 필요 여부 | 아니오 (구현 시점 정책 확인 필요) |
| 6. 신청 메뉴 경로 | 별도 신청 없이 사용 가능. 연락 이메일 제공 권장. |
| 7. 서비스 목적 예시 | 국제법·법률AI 분야 영문 연구 동향 탐색 |
| 8. 승인 절차 | 불필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `CONTACT_EMAIL` |
| 13. 동작 확인 방법 | `python main.py run --daily --source openalex --dry-run` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | API Key·무료 한도 정책이 변경될 수 있으므로 구현 직전 공식 문서를 재확인하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.openalex.org/works`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 1.0`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### Semantic Scholar (`semantic_scholar`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 아니오 / 환경변수: `SEMANTIC_SCHOLAR_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | Semantic Scholar |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://api.semanticscholar.org/api-docs/graph |
| 5. 계정 생성 필요 여부 | API Key 신청 시 필요 |
| 6. 신청 메뉴 경로 | Semantic Scholar API 페이지의 Key 요청 양식 제출 |
| 7. 서비스 목적 예시 | 중요 논문의 인용관계 탐색 및 최신 영문 논문 보강 |
| 8. 승인 절차 | 검토 후 발급 |
| 9. 무료/유료 및 쿼터 | 무료 (키 없으면 공유 쿼터) |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `SEMANTIC_SCHOLAR_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source semantic_scholar --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 키 없이 사용하면 429 가 잦습니다. rate_limit_rps 를 낮게 유지하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.semanticscholar.org/graph/v1/paper/search`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.34`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### CORE (`core`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `CORE_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | CORE |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://core.ac.uk/services/api |
| 5. 계정 생성 필요 여부 | 예 |
| 6. 신청 메뉴 경로 | CORE → Services → API → 계정 등록 후 API Key 발급 |
| 7. 서비스 목적 예시 | 오픈액세스 논문 원문 확보 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 무료 티어 제공 (상업적 이용은 별도 조건) |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `CORE_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source core --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 원문 이용조건은 개별 논문 라이선스를 따릅니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.core.ac.uk/v3/search/works`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### Unpaywall (`unpaywall`)

- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 예 / 환경변수: `CONTACT_EMAIL` / 확인상태: `VERIFIED`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | Unpaywall |
| 2. 사용 API/인증방식 | OPEN_API(불필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://unpaywall.org/products/api |
| 5. 계정 생성 필요 여부 | 아니오 |
| 6. 신청 메뉴 경로 | 별도 신청 없이 사용 가능. 모든 요청에 email 파라미터가 필요합니다. |
| 7. 서비스 목적 예시 | DOI 기반 합법적 오픈액세스 원문 위치 확인 |
| 8. 승인 절차 | 불필요 |
| 9. 무료/유료 및 쿼터 | 무료 (대량 이용은 데이터 덤프 권장) |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `CONTACT_EMAIL` |
| 13. 동작 확인 방법 | `python main.py run --daily --source crossref --dry-run` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | API Key 가 아니라 연락 이메일을 요구합니다. CONTACT_EMAIL 을 반드시 설정하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.unpaywall.org/v2`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 1.0`

---

### DOAJ (`doaj`)

- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: `DOAJ_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | DOAJ |
| 2. 사용 API/인증방식 | OPEN_API(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://doaj.org/api/docs |
| 5. 계정 생성 필요 여부 | 아니오 (일부 기능은 계정 필요) |
| 6. 신청 메뉴 경로 | 별도 신청 없이 검색 API 사용 가능 |
| 7. 서비스 목적 예시 | 검증된 오픈액세스 저널 논문 메타데이터 수집 |
| 8. 승인 절차 | 불필요 |
| 9. 무료/유료 및 쿼터 | 무료 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `DOAJ_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source doaj --dry-run` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | API 버전 경로가 변경될 수 있으므로 endpoint 를 주기적으로 확인하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://doaj.org/api/search/articles`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### arXiv (`arxiv`)

- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `VERIFIED`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | arXiv |
| 2. 사용 API/인증방식 | OPEN_API(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://info.arxiv.org/help/api/index.html |
| 5. 계정 생성 필요 여부 | 아니오 |
| 6. 신청 메뉴 경로 | 별도 신청 없이 사용 가능 |
| 7. 서비스 목적 예시 | AI·법률AI 분야 프리프린트 수집 |
| 8. 승인 절차 | 불필요 |
| 9. 무료/유료 및 쿼터 | 무료 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py run --daily --source arxiv --dry-run` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | 이용약관상 요청 간 최소 간격을 지켜야 합니다(기본 rate_limit_rps=0.33). |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://export.arxiv.org/api/query`

**수집 정책**: `download_policy: allowed` / `robots_policy: respect` / `rate_limit_rps: 0.33`

---

### SSRN (`ssrn`)

- **NONE** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `VERIFIED`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | SSRN |
| 2. 사용 API/인증방식 | NONE(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://www.ssrn.com |
| 5. 계정 생성 필요 여부 | 아니오 (자동수집 대상 아님) |
| 6. 신청 메뉴 경로 | 공개 API 를 사용하지 않습니다. 외부 학술 메타데이터로 발견 후 링크만 보존합니다. |
| 7. 서비스 목적 예시 | 법학·사회과학 working paper 의 공식 Abstract Page 연결 |
| 8. 승인 절차 | 해당 없음 |
| 9. 무료/유료 및 쿼터 | 해당 없음 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | 없음 |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | 로그인·CAPTCHA·지문 우회를 통한 자동 다운로드는 금지됩니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 0.2`

---

### Zenodo (`zenodo`)

- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 아니오 / 환경변수: `ZENODO_API_KEY` / 확인상태: `PENDING_VERIFICATION`

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | Zenodo |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://developers.zenodo.org |
| 5. 계정 생성 필요 여부 | 토큰 발급 시 필요 |
| 6. 신청 메뉴 경로 | Zenodo 로그인 → Applications → Personal access tokens |
| 7. 서비스 목적 예시 | 연구보고서·프리프린트 보강 수집 |
| 8. 승인 절차 | 즉시 발급 |
| 9. 무료/유료 및 쿼터 | 무료 |
| 10. OAuth Scope/권한 | deposit:read 등 (읽기 전용 권장) |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `ZENODO_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source zenodo --dry-run` |
| 14. 키 만료·갱신·회수 | Applications 화면에서 토큰 폐기·재발급 |
| 15. 이용약관·자동수집 주의사항 | 토큰 없이도 공개 레코드 검색이 가능합니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://zenodo.org/api/records`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---


## 부록 A. Gmail 발송 인증 (일일 브리핑)

PRD §15.4 는 SMTP 앱 비밀번호보다 **Gmail API + OAuth 2.0** 을 우선 검토하도록 규정합니다.

### A-1. Gmail API (권장)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | Google — Gmail API |
| 2. 인증방식 | OAuth 2.0 (사용자 동의 기반) |
| 3. 사전 발급 필요 | 예 — Google Cloud 프로젝트, OAuth Client, Refresh Token |
| 4. 공식 발급 페이지 | https://console.cloud.google.com |
| 5. 계정 생성 | 예 (Google 계정) |
| 6. 신청 경로 | Google Cloud Console → 프로젝트 생성 → API 및 서비스 → 라이브러리 → Gmail API 사용 설정 → OAuth 동의 화면 구성 → 사용자 인증 정보 → OAuth 클라이언트 ID(데스크톱 앱) 생성 |
| 7. 서비스 목적 예시 | 내부 리서치 수집 결과의 일일 브리핑 자동 발송 |
| 8. 승인 절차 | 내부 사용(테스트 사용자 등록) 시 별도 검수 불필요. 외부 게시 시 Google 검수 대상 |
| 9. 무료/유료·쿼터 | 무료 (발송량 쿼터는 Google 정책 준수) |
| 10. OAuth Scope | `https://www.googleapis.com/auth/gmail.send` (발송 전용 최소 권한) |
| 11. Redirect URI | 데스크톱 앱 흐름에서 `http://localhost` 계열 사용 |
| 12. 환경변수명 | `GMAIL_CLIENT_SECRET_FILE`, `GMAIL_TOKEN_FILE` |
| 13. 동작 확인 | `python main.py run --daily --source arxiv` 후 수신함 확인 |
| 14. 키 갱신·회수 | Google Cloud Console → 사용자 인증 정보에서 클라이언트 폐기, 계정 보안 설정에서 액세스 권한 철회 |
| 15. 주의사항 | `client_secret.json` 과 토큰 파일을 Git 에 커밋하지 마십시오. |
| 16. 공식 문서 확인일 | `2026-08-22` |

`config/config.yaml` 에서 `notification.email.transport: "gmail_api"` 로 설정합니다.

### A-2. SMTP 앱 비밀번호 (대안)

| 항목 | 내용 |
| --- | --- |
| 인증방식 | SMTP + 앱 비밀번호 |
| 신청 경로 | Google 계정 → 보안 → 2단계 인증 사용 설정 → 앱 비밀번호 생성 |
| 환경변수명 | `DLRCIS_SMTP_PASSWORD`, `DLRCIS_SENDER_EMAIL`, `DLRCIS_RECEIVER_EMAIL` |
| 주의사항 | 2단계 인증이 켜져 있어야 앱 비밀번호를 만들 수 있습니다. 계정 비밀번호를 그대로 쓰지 마십시오. |

## 부록 B. LLM 요약 (선택)

| 항목 | 내용 |
| --- | --- |
| 서비스 | Anthropic Claude API |
| 인증방식 | API Key |
| 공식 발급 페이지 | https://console.anthropic.com |
| 신청 경로 | Console 로그인 → API Keys → Create Key |
| 환경변수명 | `ANTHROPIC_API_KEY` |
| 동작 확인 | `config/config.yaml` 의 `summarizer.provider` 를 `llm` 로 변경 후 수집 실행 |
| 주의사항 | 키 미설정 시 자동으로 추출식 요약으로 대체됩니다. 요약 대상 원문의 외부 전송 가능 여부를 조직 정책으로 먼저 확인하십시오. |


## 부록 C. 환경변수 전체 목록

| 환경변수 | 용도 | 필수 여부 |
| --- | --- | --- |
| `KCI_API_KEY` | KCI 한국학술지인용색인 OPEN_API 인증 | 필수 |
| `RISS_API_KEY` | RISS 학술연구정보서비스 OPEN_API 인증 | 필수 |
| `SCIENCEON_API_KEY` | ScienceON (KISTI) OPEN_API 인증 | 필수 |
| `NKIS_API_KEY` | NKIS 국가정책연구포털 OPEN_API 인증 | 필수 |
| `DATA_GO_KR_API_KEY` | PRISM 정책연구관리시스템 OPEN_API 인증 | 필수 |
| `LAW_GO_KR_OC` | 국가법령정보 공동활용 OPEN_API 인증 | 필수 |
| `CONTACT_EMAIL` | Crossref OPEN_API 인증 | 선택 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar OPEN_API 인증 | 선택 |
| `CORE_API_KEY` | CORE OPEN_API 인증 | 필수 |
| `DOAJ_API_KEY` | DOAJ OPEN_API 인증 | 선택 |
| `ZENODO_API_KEY` | Zenodo OPEN_API 인증 | 선택 |
| `DLRCIS_SENDER_EMAIL` | 브리핑 발신 주소 | 필수 |
| `DLRCIS_RECEIVER_EMAIL` | 브리핑 수신 주소 | 필수 |
| `DLRCIS_SMTP_PASSWORD` | SMTP 앱 비밀번호 | SMTP 사용 시 필수 |
| `GMAIL_CLIENT_SECRET_FILE` | Gmail OAuth 클라이언트 시크릿 파일 경로 | Gmail API 사용 시 |
| `GMAIL_TOKEN_FILE` | Gmail OAuth 토큰 파일 경로 | Gmail API 사용 시 |
| `ANTHROPIC_API_KEY` | LLM 요약(선택) | 선택 |

> 마지막 생성: 2026-08-22 · `python main.py api-guide` 로 재생성할 수 있습니다.
