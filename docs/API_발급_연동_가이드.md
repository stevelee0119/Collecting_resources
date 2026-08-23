# API 발급·연동 가이드

> 이 문서는 `config/sources.yaml` 에서 **자동 생성**됩니다.
> 수정하려면 `config/sources.yaml` 을 고친 뒤 `python main.py api-guide` 를 다시 실행하십시오.
>
> - 생성일: 2026-08-23
> - Source Registry 버전: `2026.08.22-1`
> - 대상 소스: 전체 21개 (사전 발급·승인 필요 13개)

## 0. 조치 현황 한눈에 보기

> 이 표는 문서를 생성한 시점(`python main.py api-guide` 실행 환경)에서
> 환경변수가 실제로 읽히는지 확인한 결과입니다.

**✅ 조치 완료 (6건)** — 바로 사용 가능

- KCI 한국학술지인용색인 (`kci` / OAI_PMH)
- Crossref (`crossref` / OPEN_API)
- Semantic Scholar (`semantic_scholar` / OPEN_API)
- DOAJ (`doaj` / OPEN_API)
- arXiv (`arxiv` / OPEN_API)
- Zenodo (`zenodo` / OPEN_API)

**🟡 일부 완료 (0건)** — 남은 값 추가 필요

- (없음)

**⬜ 추가 조치 필요 (15건)**

- KCI 한국학술지인용색인 (`kci` / OPEN_API) — 발급 후 `.env` 에 `KCI_API_KEY` 설정
- ScienceON (KISTI) (`scienceon` / OPEN_API) — 발급 후 `.env` 에 `SCIENCEON_API_KEY` 설정
- NKIS 국가정책연구포털 (`nkis` / OPEN_API) — 공식 문서(https://www.nkis.re.kr/openDesc.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- PRISM 정책연구관리시스템 (`prism` / OPEN_API) — 발급 후 `.env` 에 `DATA_GO_KR_API_KEY` 설정
- 국가법령정보 공동활용 (`law_go_kr` / OPEN_API) — 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정
- 국회입법조사처 (`nars` / OPEN_API) — 공식 문서(https://www.data.go.kr/data/15125970/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 사법정책연구원 (`jpri` / RSS) — 공식 문서(https://jpri.scourt.go.kr/post/postList.do?boardSeq=7&menuSeq=11&lang=ko)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 법무연수원 (`ioj` / RSS) — 공식 문서(https://book.ioj.go.kr/library)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 한국형사·법무정책연구원 (`kicj` / RSS) — 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 한국형사·법무정책연구원 (`kicj` / OPEN_API) — 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 국가인권위원회 (`humanrights` / RSS) — 공식 문서(https://library.humanrights.go.kr/)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 한국국방연구원 (KIDA) (`kida` / RSS) — 공식 문서(https://kida.re.kr/frt/contents/frtContents.do?sidx=2127&depth=3)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- OpenAlex (`openalex` / OPEN_API) — 발급 후 `.env` 에 `OPENALEX_API_KEY` 설정
- CORE (`core` / OPEN_API) — 발급 후 `.env` 에 `CORE_API_KEY` 설정
- Unpaywall (`unpaywall` / OPEN_API) — 발급 후 `.env` 에 `CONTACT_EMAIL` 설정

**➖ 자동수집 대상 아님 (2건)** — 조치 불필요

- RISS 학술연구정보서비스 (`riss` / OPEN_API)
- SSRN (`ssrn` / NONE)

### 상태 표시의 의미

| 표시 | 의미 |
| --- | --- |
| ✅ 완료 | 바로 사용 가능 (인증 불필요이거나 인증정보가 설정되어 있음) |
| 🟡 일부 완료 | 인증정보 일부만 설정됨 — 남은 값을 추가해야 동작 |
| ⬜ 조치 필요 | 발급 또는 엔드포인트 입력이 필요 |
| ➖ 대상 아님 | 공식적으로 자동수집 대상이 아님 (추가 조치 불필요) |

---

## 0-1. 인증정보를 프로그램에 전달하는 방법

발급받은 값은 **프로그램이 읽을 수 있는 위치**에 있어야 합니다.
값을 어디에 보관했는지에 따라 동작 여부가 달라집니다.

| 보관 위치 | 프로그램이 읽는가 | 비고 |
| --- | --- | --- |
| 프로젝트 루트의 `.env` | **읽음** | 로컬 실행 시 표준 방법 (`.gitignore` 로 제외됨) |
| OS 환경변수 (`export` / `setx`) | **읽음** | 서버·스케줄러 운영 시 |
| GitHub **Secrets** + Actions 워크플로 | 워크플로가 `env:` 로 주입하면 읽음 | 워크플로 파일이 있어야 함 |
| GitHub **Variables** | **읽지 않음** | 아래 경고 참조 |

> ⚠ **GitHub Actions Variables 에 API Key 를 넣지 마십시오.**
> Variables 는 **평문으로 저장**되며 저장소 읽기 권한이 있는 사람이 볼 수 있고
> 워크플로 로그에도 그대로 남습니다. API Key·토큰·비밀번호는 반드시
> **Secrets** 에 저장하십시오. 또한 Variables/Secrets 는 GitHub Actions 실행 중에만
> 존재하므로, 로컬이나 별도 서버에서 실행할 때는 `.env` 또는 OS 환경변수가 필요합니다.

---

## 0-2. 읽기 전 안내

이 가이드는 **비개발자도 인증정보를 직접 발급받아 시스템에 연결할 수 있도록** 작성되었습니다.

### 보안 원칙 (PRD §5.1)

1. 실제 API Key, Client Secret, Refresh Token 을 **이 문서에 기록하지 마십시오.**
2. 이 문서에는 **환경변수명만** 적습니다. 예: `KCI_API_KEY`
3. 실제 값은 프로젝트 루트의 `.env` (Git 제외) 또는 OS Secret Store 에 저장합니다.
4. `.env.example` 에는 변수명과 설명만 넣고 실제 값은 넣지 않습니다.

### 최신성 원칙

API 발급·인증 방식은 변경될 수 있습니다. **Connector 를 실제로 연결하기 직전에 공식 문서를 다시 확인**하십시오.
블로그·카페·개인 튜토리얼은 보조자료로만 사용하고, 발급절차·쿼터·가격·권한은 공식 문서를 기준으로 판단합니다.

각 항목의 **확인상태**와 **확인근거**는 다음을 뜻합니다.

| 값 | 의미 |
| --- | --- |
| `VERIFIED` | 공식 문서로 엔드포인트·인증방식을 확정함 (확인근거 URL 기재) |
| `PENDING_VERIFICATION` | 아직 확정되지 않음 — 운영 전 공식 문서 확인 필요 |
| 확인근거 · 공식 문서 직접 열람 | 공식 페이지를 직접 열어 확인 |
| 확인근거 · 공식 문서 검색결과 기준 | 공식 문서의 검색 결과로 확인 (원문 재확인 권장) |

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

| 소스 | 인증방식 | 환경변수 | 조치 현황 | 남은 조치 |
| --- | --- | --- | --- | --- |
| KCI 한국학술지인용색인 (`kci`) | OPEN_API / API Key 필요 | `KCI_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `KCI_API_KEY` 설정 |
| RISS 학술연구정보서비스 (`riss`) | OPEN_API / 기관 승인 필요 | `RISS_API_KEY` | ➖ 대상 아님 | 자동수집 대상이 아닙니다. 추가 조치 불필요. |
| ScienceON (KISTI) (`scienceon`) | OPEN_API / API Key 필요 | `SCIENCEON_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `SCIENCEON_API_KEY` 설정 |
| NKIS 국가정책연구포털 (`nkis`) | OPEN_API / API Key 필요 | `NKIS_API_KEY` | ⬜ 조치 필요 | 공식 문서(https://www.nkis.re.kr/openDesc.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력 |
| PRISM 정책연구관리시스템 (`prism`) | OPEN_API / API Key 필요 | `DATA_GO_KR_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `DATA_GO_KR_API_KEY` 설정 |
| 국가법령정보 공동활용 (`law_go_kr`) | OPEN_API / API Key 필요 | `LAW_GO_KR_OC` | ⬜ 조치 필요 | 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정 |
| 국회입법조사처 (`nars`) | OPEN_API / API Key 필요 | `DATA_GO_KR_API_KEY` | ⬜ 조치 필요 | 공식 문서(https://www.data.go.kr/data/15125970/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력 |
| 한국형사·법무정책연구원 (`kicj`) | OPEN_API / API Key 필요 | `DATA_GO_KR_API_KEY` | ⬜ 조치 필요 | 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력 |
| OpenAlex (`openalex`) | OPEN_API / API Key 필요 | `OPENALEX_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `OPENALEX_API_KEY` 설정 |
| Semantic Scholar (`semantic_scholar`) | OPEN_API / API Key 필요 | `SEMANTIC_SCHOLAR_API_KEY` | ✅ 완료 | 별도 발급 없이 사용 가능 |
| CORE (`core`) | OPEN_API / API Key 필요 | `CORE_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `CORE_API_KEY` 설정 |
| Unpaywall (`unpaywall`) | OPEN_API / 불필요 | `CONTACT_EMAIL` | ⬜ 조치 필요 | 발급 후 `.env` 에 `CONTACT_EMAIL` 설정 |
| Zenodo (`zenodo`) | OPEN_API / API Key 필요 | `ZENODO_API_KEY` | ✅ 완료 | 별도 발급 없이 사용 가능 |

## 2. 별도 발급 없이 사용 가능한 소스

- **사법정책연구원** (`jpri`) — 별도 발급 없이 사용 가능
- **법무연수원** (`ioj`) — 별도 발급 없이 사용 가능
- **국가인권위원회** (`humanrights`) — 별도 발급 없이 사용 가능
- **한국국방연구원 (KIDA)** (`kida`) — 별도 발급 없이 사용 가능
- **Crossref** (`crossref`) — 별도 발급 없이 사용 가능 (연락 이메일 `CONTACT_EMAIL` 권장)
- **DOAJ** (`doaj`) — 별도 발급 없이 사용 가능
- **arXiv** (`arxiv`) — 별도 발급 없이 사용 가능
- **SSRN** (`ssrn`) — 별도 발급 없이 사용 가능

> Crossref·OpenAlex 는 연락 이메일을 제공하면 polite pool 로 안정적인 응답을 받습니다.
> Unpaywall 은 모든 요청에 이메일이 **필수**입니다.

## 3. 소스별 상세 발급 절차

### KCI 한국학술지인용색인 (`kci`)

- **조치 현황: ✅ 완료** — 별도 발급 없이 사용 가능
- **OAI_PMH** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `VERIFIED`
  - 확인근거: https://www.kci.go.kr/kciportal/po/openapi/openDataOaiPmhView.kci (2026-08-22, 공식 문서 검색결과 기준)
- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `KCI_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `KCI_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://www.kci.go.kr/kciportal/po/openapi/openApiConnSamp.kci (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | KCI 한국학술지인용색인 |
| 2. 사용 API/인증방식 | OAI_PMH(불필요), OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.kci.go.kr/kciportal/po/openapi/openApiList.kci |
| 5. 계정 생성 필요 여부 | 예 (KCI 회원가입) |
| 6. 신청 메뉴 경로 | KCI 포털 → Open API 목록(openApiList.kci) → 사용하려는 API 선택 후 이용 신청. 활용방법은 openApiConnSamp.kci, 명세서는 openDataView.kci 에서 확인 |
| 7. 서비스 목적 예시 | 군사법·형사법 분야 국내 학술논문 메타데이터의 정기 수집 및 사내 리서치 색인 구축 |
| 8. 승인 절차 | 신청 후 운영기관 검토 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 (API Key 방식) |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `KCI_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source kci --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | OAI-PMH(https://open.kci.go.kr/oai/request)는 별도 인증 없이 사용 가능한 것으로 안내되어 있어 이 경로를 우선 사용합니다. Open API 는 apiCode/key/title/author/pubiYr 파라미터를 사용하며, 일자 범위가 아닌 발행연도(pubiYr) 단위 필터만 제공합니다. 제공 API: articleSearch / articleDetail / referenceSearch / citation / citationDetail |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://open.kci.go.kr/oai/request`
  - `https://open.kci.go.kr/po/openapi/openApiSearch.kci`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### RISS 학술연구정보서비스 (`riss`)

- **조치 현황: ➖ 대상 아님** — 자동수집 대상이 아닙니다. 추가 조치 불필요.
- **OPEN_API** — 인증: 기관 승인 필요 / 사전 발급 필요: 예 / 환경변수: `RISS_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://www.riss.kr/apicenter/apiMain.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | RISS 학술연구정보서비스 |
| 2. 사용 API/인증방식 | OPEN_API(기관 승인 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.riss.kr/apicenter/apiMain.do |
| 5. 계정 생성 필요 여부 | 예 |
| 6. 신청 메뉴 경로 | RISS API 센터(apicenter/apiMain.do)에서 제공 API 확인 후 신청 |
| 7. 서비스 목적 예시 | 국방·법률 주제 학술자료의 서지 메타데이터 수집 (원문 자동 다운로드 없음) |
| 8. 승인 절차 | 기관 검토·승인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `RISS_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source riss --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | RISS API 센터가 공개하는 API 는 상호대차(ILL)·E-DDS 신청, Rinfo 통계, FRIC 소장자원 검색용이며 일반 학술 서지 검색 API 는 확인되지 않았습니다. 따라서 이 시스템은 RISS 를 직접 조회하지 않고 LINK_ONLY 로만 사용합니다. 화면상 '원문있음' 표시가 자동 다운로드 권한을 의미하지 않습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 0.2`

---

### ScienceON (KISTI) (`scienceon`)

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `SCIENCEON_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `SCIENCEON_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://scienceon.kisti.re.kr/apigateway/api/way/service/arti/serviceArtiSearchApi.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | ScienceON (KISTI) |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://scienceon.kisti.re.kr/apigateway/api/main/mainForm.do |
| 5. 계정 생성 필요 여부 | 예 (KISTI 통합회원) |
| 6. 신청 메뉴 경로 | ScienceON → OpenAPI(por/oapi/openApi.do) 신청 → API Gateway(apigateway/api/main/mainForm.do)에서 client_id 와 ACCESS_TOKEN 확인 |
| 7. 서비스 목적 예시 | 국내외 학술논문·연구보고서 메타데이터 및 오픈액세스 원문 위치 탐색 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | API 별 이용조건 확인 필요 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `SCIENCEON_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source scienceon --dry-run` |
| 14. 키 만료·갱신·회수 | 토큰 만료일이 있으므로 API Gateway 에서 갱신 상태를 확인하십시오. |
| 15. 이용약관·자동수집 주의사항 | 인증에 client_id 와 token(ACCESS_TOKEN) 두 값이 모두 필요합니다 (SCIENCEON_CLIENT_ID, SCIENCEON_API_KEY). 요청 파라미터는 version/action/target/searchQuery/curPage/rowCount 이며 searchQuery 는 JSON 문자열입니다. AccessON 오픈액세스 검색은 별도 이용조건이 적용될 수 있습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://apigateway.kisti.re.kr/openapicall.do`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### NKIS 국가정책연구포털 (`nkis`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://www.nkis.re.kr/openDesc.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `NKIS_API_KEY` / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://www.nkis.re.kr/openSvcList.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | NKIS 국가정책연구포털 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.nkis.re.kr/openDesc.do |
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

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `DATA_GO_KR_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `DATA_GO_KR_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://www.data.go.kr/data/15080254/openapi.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | PRISM 정책연구관리시스템 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.data.go.kr/data/15080254/openapi.do |
| 5. 계정 생성 필요 여부 | 예 (공공데이터포털 회원가입) |
| 6. 신청 메뉴 경로 | 공공데이터포털 → '행정안전부_정책연구 과제정보'(15080254) → 활용신청. 오퍼레이션: getResearchList_v2 / getResearchDetail_v2 / pnnMetaData_v2 |
| 7. 서비스 목적 예시 | 중앙·지방정부 정책연구용역 보고서의 정기 수집 |
| 8. 승인 절차 | 자동승인 또는 기관 검토 (API 별 상이) |
| 9. 무료/유료 및 쿼터 | 공공데이터포털 기준 무료(트래픽 한도 있음) |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `DATA_GO_KR_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source prism --dry-run` |
| 14. 키 만료·갱신·회수 | 공공데이터포털 마이페이지에서 활용기간 연장 신청 |
| 15. 이용약관·자동수집 주의사항 | 일반 인증키가 Encoding/Decoding 두 형태로 발급되므로 구분해서 사용하십시오. 응답 필드명은 데이터셋 상세페이지의 '출력결과' 표를 보고 config/sources.yaml 의 field_map 을 맞춰야 합니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://apis.data.go.kr/1741000/prism_v2/getResearchList_v2`

**수집 정책**: `download_policy: allowed` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### 국가법령정보 공동활용 (`law_go_kr`)

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `LAW_GO_KR_OC` / 확인상태: `VERIFIED`
  - 확인근거: https://open.law.go.kr/LSO/openApi/guideList.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국가법령정보 공동활용 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://open.law.go.kr/LSO/openApi/guideList.do |
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
| 15. 이용약관·자동수집 주의사항 | OC 는 API Key 가 아니라 사용자 식별자이지만 동일하게 .env 로 관리합니다. 요청변수는 OC/target/type/query/display/page 이며, 판례 목록은 prncYd(선고일자 범위)를 지원합니다. target 코드: law(법령) admrul(행정규칙) prec(판례) expc(법령해석례) ordin(자치법규). 동일 데이터가 공공데이터포털에도 등재되어 있습니다(예: 법제처_판례 목록 조회 15059269). |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://www.law.go.kr/DRF/lawSearch.do`

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 1.0`

---

### 국회입법조사처 (`nars`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://www.data.go.kr/data/15125970/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `DATA_GO_KR_API_KEY` / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://www.data.go.kr/data/15125970/openapi.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국회입법조사처 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.data.go.kr/data/15125970/openapi.do |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `DATA_GO_KR_API_KEY` |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 공식 RSS 주소는 확인되지 않았습니다. 대신 공공데이터포털에 연구보고서(15125970)와 제공자료 통합 API(15126137)가 등재되어 있으므로 그 상세주소를 endpoint 에 입력하십시오. 열린국회정보(open.assembly.go.kr)도 대체 경로로 검토할 수 있습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### 사법정책연구원 (`jpri`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://jpri.scourt.go.kr/post/postList.do?boardSeq=7&menuSeq=11&lang=ko)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://jpri.scourt.go.kr/post/postList.do?boardSeq=7&menuSeq=11&lang=ko (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 사법정책연구원 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://jpri.scourt.go.kr/post/postList.do?boardSeq=7&menuSeq=11&lang=ko |
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
| 15. 이용약관·자동수집 주의사항 | 공식 RSS 는 확인되지 않았습니다. 발간자료(연구보고서·외국사법제도연구·학술행사자료)는 게시판(postList.do)으로 제공되므로, 자동수집 전 robots.txt 와 이용약관을 확인하고 허용되는 경우에만 전용 Adapter 를 구성하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 법무연수원 (`ioj`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://book.ioj.go.kr/library)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://book.ioj.go.kr/library (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 법무연수원 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://book.ioj.go.kr/library |
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
| 15. 이용약관·자동수집 주의사항 | 공식 RSS 는 확인되지 않았습니다. 발간물은 법무연수원 전자도서관(book.ioj.go.kr)에서 제공되므로 해당 시스템의 공개 인터페이스를 먼저 확인하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 한국형사·법무정책연구원 (`kicj`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://www.kicj.re.kr/ (2026-08-22, 공식 문서 검색결과 기준)
- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `DATA_GO_KR_API_KEY` / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://www.data.go.kr/data/15140051/openapi.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 한국형사·법무정책연구원 |
| 2. 사용 API/인증방식 | RSS(불필요), OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://www.data.go.kr/data/15140051/openapi.do |
| 5. 계정 생성 필요 여부 | 공식 문서 확인 필요 |
| 6. 신청 메뉴 경로 | 공식 문서 확인 필요 |
| 7. 서비스 목적 예시 | 공식 문서 확인 필요 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `DATA_GO_KR_API_KEY` |
| 13. 동작 확인 방법 | `python main.py doctor` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 기관 자체 RSS 는 확인되지 않았습니다. 다만 공공데이터포털에 교정통계연보(15140051) 등 KICJ 데이터셋이 등재되어 있으므로, 필요한 데이터셋의 상세주소를 endpoint 에 입력해 사용하십시오. 연구보고서 원문은 기관 홈페이지 발간물 게시판에서 제공됩니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS, OPEN_API

---

### 국가인권위원회 (`humanrights`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://library.humanrights.go.kr/)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://library.humanrights.go.kr/ (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국가인권위원회 |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://library.humanrights.go.kr/ |
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
| 15. 이용약관·자동수집 주의사항 | 공식 RSS 는 확인되지 않았습니다. 결정례·판례·발간물은 인권도서관(library.humanrights.go.kr)에서 제공되므로 해당 시스템의 공개 인터페이스를 먼저 확인하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 한국국방연구원 (KIDA) (`kida`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://kida.re.kr/frt/contents/frtContents.do?sidx=2127&depth=3)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- **RSS** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://kida.re.kr/frt/contents/frtContents.do?sidx=2127&depth=3 (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 한국국방연구원 (KIDA) |
| 2. 사용 API/인증방식 | RSS(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://kida.re.kr/frt/contents/frtContents.do?sidx=2127&depth=3 |
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
| 15. 이용약관·자동수집 주의사항 | 기관 홈페이지에 '공공데이터 소개' 안내가 있으므로 그 페이지에서 제공 형식과 이용조건을 확인한 뒤 endpoint 를 입력하십시오. 공식 RSS 주소는 확인되지 않았습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### Crossref (`crossref`)

- **조치 현황: ✅ 완료** — 별도 발급 없이 사용 가능
- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: `CONTACT_EMAIL` / 확인상태: `VERIFIED`
  - 확인근거: https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/ (2026-08-22, 공식 문서 검색결과 기준)

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

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `OPENALEX_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `OPENALEX_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://developers.openalex.org/api-reference/introduction (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | OpenAlex |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://openalex.org/settings/api |
| 5. 계정 생성 필요 여부 | 예 (API Key 발급 필요) |
| 6. 신청 메뉴 경로 | openalex.org 로그인 → Settings → API 에서 무료 키 발급 |
| 7. 서비스 목적 예시 | 국제법·법률AI 분야 영문 연구 동향 탐색 |
| 8. 승인 절차 | 불필요 (즉시 발급) |
| 9. 무료/유료 및 쿼터 | 무료 키에 일일 예산이 배정되고 초과분은 사용량 기반 과금. 키가 없으면 시험용 크레딧 100건 소진 후 409 반환 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `OPENALEX_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source openalex --dry-run` |
| 14. 키 만료·갱신·회수 | openalex.org/settings/api 에서 키 재발급·폐기 |
| 15. 이용약관·자동수집 주의사항 | 2026-02-13 부터 모든 요청에 API Key 가 필수가 되었고 polite pool 과 mailto 파라미터는 폐지되었습니다. 사용량 기반 과금이므로 rate_limit_rps 를 낮게 유지하고 max_items_per_source 로 호출량을 통제하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.openalex.org/works`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### Semantic Scholar (`semantic_scholar`)

- **조치 현황: ✅ 완료** — 별도 발급 없이 사용 가능
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 아니오 / 환경변수: `SEMANTIC_SCHOLAR_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://api.semanticscholar.org/api-docs/graph (2026-08-22, 공식 문서 검색결과 기준)

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
| 15. 이용약관·자동수집 주의사항 | 키 없는 요청은 모든 미인증 사용자가 하나의 공유 키를 나눠 쓰므로 429 가 잦습니다. 개인 키를 받으면 전 엔드포인트에서 초당 1회가 보장됩니다. 대량 조회에는 /graph/v1/paper/search/bulk 를 사용하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.semanticscholar.org/graph/v1/paper/search`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.34`

---

### CORE (`core`)

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `CORE_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `CORE_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://core.ac.uk/services/api (2026-08-22, 공식 문서 검색결과 기준)

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
| 15. 이용약관·자동수집 주의사항 | v3 는 쿼리 파라미터가 아니라 Authorization: Bearer 헤더로 인증합니다. 원문 이용조건은 개별 논문 라이선스를 따릅니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://api.core.ac.uk/v3/search/works`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### Unpaywall (`unpaywall`)

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `CONTACT_EMAIL` 설정
- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 예 / 환경변수: `CONTACT_EMAIL` / 확인상태: `VERIFIED`
  - 확인근거: https://unpaywall.org/products/api (2026-08-22, 공식 문서 검색결과 기준)

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

- **조치 현황: ✅ 완료** — 별도 발급 없이 사용 가능
- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: `DOAJ_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://doaj.org/api/v4/docs (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | DOAJ |
| 2. 사용 API/인증방식 | OPEN_API(불필요) |
| 3. 사전 발급 필요 여부 | 아니오 |
| 4. 공식 발급/신청 페이지 | https://doaj.org/api/v4/docs |
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
| 15. 이용약관·자동수집 주의사항 | 현재 버전은 v4 이며 /api 와 /api/v4 양쪽에서 제공됩니다(2024-06 전환). pageSize 최대값은 100 입니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://doaj.org/api/v4/search/articles`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### arXiv (`arxiv`)

- **조치 현황: ✅ 완료** — 별도 발급 없이 사용 가능
- **OPEN_API** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `VERIFIED`
  - 확인근거: https://info.arxiv.org/help/api/index.html (2026-08-22, 공식 문서 검색결과 기준)

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

- **조치 현황: ➖ 대상 아님** — 자동수집 대상이 아닙니다. 추가 조치 불필요.
- **NONE** — 인증: 불필요 / 사전 발급 필요: 아니오 / 환경변수: 없음 / 확인상태: `VERIFIED`
  - 확인근거: https://www.ssrn.com/index.cfm/en/terms-of-use/ (2026-08-22, 공식 문서 검색결과 기준)

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

- **조치 현황: ✅ 완료** — 별도 발급 없이 사용 가능
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 아니오 / 환경변수: `ZENODO_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://developers.zenodo.org (2026-08-22, 공식 문서 검색결과 기준)

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
| 16. 공식 문서 확인일 | `2026-08-23` |

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
| `OPENALEX_API_KEY` | OpenAlex OPEN_API 인증 | 필수 |
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

> 마지막 생성: 2026-08-23 · `python main.py api-guide` 로 재생성할 수 있습니다.
