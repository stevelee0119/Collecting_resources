# API 발급·연동 가이드

> 이 문서는 `config/sources.yaml` 에서 **자동 생성**됩니다.
> 수정하려면 `config/sources.yaml` 을 고친 뒤 `python main.py api-guide` 를 다시 실행하십시오.
>
> - 생성일: 2026-08-24
> - Source Registry 버전: `2026.08.22-1`
> - 대상 소스: 전체 22개 (사전 발급·승인 필요 15개)

## 0. 조치 현황 한눈에 보기

> **평가 환경: `로컬/서버 실행 — GitHub Secrets 는 이 환경에 전달되지 않으므로, Secrets 에만 값을 넣으셨다면 '조치 필요'로 표시됩니다.`**
>
> 아래 상태는 이 문서를 생성한 환경에서 환경변수가 **실제로 읽히는지** 확인한 결과입니다.
> GitHub Secrets 에 값을 넣으셨다면 그 값은 **Actions 워크플로 실행 중에만** 존재하므로,
> 로컬에서 생성한 문서에는 "조치 필요"로 표시됩니다. 실제 상태를 보려면
> `.github/workflows/credential-check.yml` 을 수동 실행하십시오 (§0-3).

**✅ 조치 완료 (6건)** — 바로 사용 가능

- KCI 한국학술지인용색인 (`kci` / OAI_PMH)
- Crossref (`crossref` / OPEN_API)
- Semantic Scholar (`semantic_scholar` / OPEN_API)
- DOAJ (`doaj` / OPEN_API)
- arXiv (`arxiv` / OPEN_API)
- Zenodo (`zenodo` / OPEN_API)

**🟡 일부 완료 (0건)** — 남은 값 추가 필요

- (없음)

**⬜ 추가 조치 필요 (16건)**

- KCI 한국학술지인용색인 (`kci` / OPEN_API) — 발급 후 `.env` 에 `KCI_API_KEY` 설정
- NKIS 국가정책연구포털 (`nkis` / OPEN_API) — 발급 후 `.env` 에 `NKIS_API_KEY` 설정
- 디지털집현전 (국가지식정보 통합플랫폼) (`kknowledge` / OPEN_API) — 발급 후 `.env` 에 `KKNOWLEDGE_API_KEY` 설정
- PRISM 정책연구관리시스템 (`prism` / OPEN_API) — 발급 후 `.env` 에 `DATA_GO_KR_API_KEY` 설정
- 국가법령정보 공동활용 (`law_go_kr` / OPEN_API) — 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정
- 국회입법조사처 (`nars` / OPEN_API) — 발급 후 `.env` 에 `ASSEMBLY_API_KEY` 설정
- 사법정책연구원 (`jpri` / RSS) — 공식 문서(https://jpri.scourt.go.kr/post/postList.do?boardSeq=7&menuSeq=11&lang=ko)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 법무연수원 (`ioj` / RSS) — 공식 문서(https://book.ioj.go.kr/library)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 한국형사·법무정책연구원 (`kicj` / RSS) — 공식 문서(https://www.kicj.re.kr/)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 한국형사·법무정책연구원 (`kicj` / OPEN_API) — 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 국가인권위원회 (`humanrights` / RSS) — 공식 문서(https://library.humanrights.go.kr/)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- 국가인권위원회 (`humanrights` / OPEN_API) — 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정
- 한국국방연구원 (KIDA) (`kida` / RSS) — 공식 문서(https://kida.re.kr/frt/contents/frtContents.do?sidx=2127&depth=3)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
- OpenAlex (`openalex` / OPEN_API) — 발급 후 `.env` 에 `OPENALEX_API_KEY` 설정
- CORE (`core` / OPEN_API) — 발급 후 `.env` 에 `CORE_API_KEY` 설정
- Unpaywall (`unpaywall` / OPEN_API) — 발급 후 `.env` 에 `CONTACT_EMAIL` 설정

**➖ 자동수집 대상 아님 (2건)** — 조치 불필요

- RISS 학술연구정보서비스 (`riss` / OPEN_API)
- SSRN (`ssrn` / NONE)

**⛔ 수집 대상 제외 (1건)** — 운영 판단으로 제외, 조치 불필요

- ScienceON (KISTI) (`scienceon` / OPEN_API)

### 상태 표시의 의미

| 표시 | 의미 |
| --- | --- |
| ✅ 완료 | 이 환경에서 바로 사용 가능 (인증 불필요이거나 인증정보가 읽힘) |
| 🟡 일부 완료 | 인증정보 일부만 설정됨 — 남은 값을 추가해야 동작 |
| ⬜ 조치 필요 | 발급·엔드포인트 입력이 필요하거나, 값이 이 환경에 전달되지 않음 |
| ➖ 대상 아님 | 공식적으로 자동수집 대상이 아님 (추가 조치 불필요) |
| ⛔ 제외 | 운영 판단으로 수집 대상에서 제외 (사유는 소스별 상세 참조) |

---

## 0-1. 인증정보는 3단계를 모두 통과해야 동작합니다

키를 발급받았다고 해서 프로그램이 쓸 수 있는 것은 아닙니다.
아래 3단계가 **모두** 충족되어야 해당 소스가 실제로 수집됩니다.

```
1단계 발급     기관에서 API Key / 승인 / 식별자를 받았는가
   ↓
2단계 저장     안전한 곳에 보관했는가 (.env / OS 환경변수 / GitHub Secrets)
   ↓
3단계 전달     실행 시점에 프로그램의 환경변수로 주입되는가   ← 여기서 자주 막힙니다
   ↓
4단계 엔드포인트  config/sources.yaml 의 endpoint 가 채워져 있는가
```

### 보관 위치별 전달 여부

| 보관 위치 | 실행 환경 | 전달되는가 | 필요한 것 |
| --- | --- | --- | --- |
| `.env` (프로젝트 루트) | 로컬 / 서버 | **전달됨** | 없음 (`python-dotenv` 가 자동 로드) |
| OS 환경변수 | 로컬 / 서버 | **전달됨** | `export` (Linux/macOS) 또는 `setx` (Windows) |
| GitHub **Secrets** | GitHub Actions | 워크플로가 `env:` 로 매핑해야 전달됨 | **워크플로 파일** |
| GitHub **Secrets** | 로컬 / 서버 | **전달 안 됨** | 별도로 `.env` 필요 |
| GitHub **Variables** | 모든 환경 | 권장하지 않음 | — (아래 경고) |

> ⚠ **GitHub Actions Variables 에 API Key 를 넣지 마십시오.**
> Variables 는 **평문으로 저장**되어 저장소 읽기 권한자가 볼 수 있고 워크플로 로그에도 남습니다.
> API Key·토큰·비밀번호는 **Secrets** 에 저장하는 것이 맞습니다.
> (이미 Variables 에 넣었던 값이 있다면 Secrets 로 옮긴 뒤 Variables 에서 삭제하고,
> 노출 가능성이 있으므로 **키를 재발급**하는 것이 안전합니다.)

---

## 0-2. GitHub Secrets 에 등록할 이름

프로그램은 아래 **정확한 이름**의 환경변수를 읽습니다.
Secrets 이름을 이와 동일하게 맞추면 워크플로에서 그대로 매핑할 수 있습니다.

| 환경변수 이름 | 용도 | 지금 등록이 필요한가 |
| --- | --- | --- |
| `KCI_API_KEY` | KCI 한국학술지인용색인 OPEN_API | ✅ 필수 |
| `RISS_API_KEY` | RISS 학술연구정보서비스 OPEN_API | ➖ 불필요 (엔드포인트 미확정) |
| `SCIENCEON_API_KEY` | ScienceON (KISTI) OPEN_API | ⛔ 불필요 (수집 대상 제외) |
| `NKIS_API_KEY` | NKIS 국가정책연구포털 OPEN_API | ✅ 필수 |
| `KKNOWLEDGE_API_KEY` | 디지털집현전 (국가지식정보 통합플랫폼) OPEN_API | ✅ 필수 |
| `DATA_GO_KR_API_KEY` | PRISM 정책연구관리시스템 OPEN_API | ✅ 필수 |
| `LAW_GO_KR_OC` | 국가법령정보 공동활용 OPEN_API | ✅ 필수 |
| `ASSEMBLY_API_KEY` | 국회입법조사처 OPEN_API | ✅ 필수 |
| `CONTACT_EMAIL` | Crossref OPEN_API | 선택 (있으면 쿼터·속도 유리) |
| `OPENALEX_API_KEY` | OpenAlex OPEN_API | ✅ 필수 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar OPEN_API | 선택 (있으면 쿼터·속도 유리) |
| `CORE_API_KEY` | CORE OPEN_API | ✅ 필수 |
| `DOAJ_API_KEY` | DOAJ OPEN_API | 선택 (있으면 쿼터·속도 유리) |
| `ZENODO_API_KEY` | Zenodo OPEN_API | 선택 (있으면 쿼터·속도 유리) |
| `DLRCIS_SENDER_EMAIL` | 브리핑 발신 주소 | ✅ 알림 사용 시 필수 |
| `DLRCIS_RECEIVER_EMAIL` | 브리핑 수신 주소 | ✅ 알림 사용 시 필수 |
| `DLRCIS_SMTP_PASSWORD` | Gmail 앱 비밀번호 | ✅ SMTP 사용 시 필수 |
| `ANTHROPIC_API_KEY` | LLM 요약 (선택) | 선택 |

> Secrets 는 설계상 **값을 다시 읽을 수 없습니다**(write-only). 등록 여부는
> 이름 목록으로만 확인되며, 실제 동작 여부는 워크플로를 실행해 확인해야 합니다.

---

## 0-3. Secrets 가 실제로 동작하는지 확인하는 방법

`.github/workflows/credential-check.yml` 워크플로를 **수동 실행**하면
Secrets 가 주입된 상태에서 점검이 수행됩니다.

```
GitHub 저장소 → Actions 탭 → "인증정보 점검" → Run workflow
```

실행 결과에서 확인할 수 있는 것:

- 각 소스가 `[OK]` 인지 `[SKIP]` 인지 (=인증정보가 실제로 읽혔는지)
- 이 문서가 Secrets 기준으로 재생성되어 **artifact 로 첨부**됨
- 키 값 자체는 출력되지 않습니다 (GitHub 이 자동 마스킹하며, 코드도 마스킹 처리)

> 워크플로는 `workflow_dispatch` 전용이라 **직접 실행할 때만** 동작합니다.
> 자동 수집 스케줄을 원하시면 §부록 D 를 참고하십시오.

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
| ScienceON (KISTI) (`scienceon`) | OPEN_API / API Key 필요 | `SCIENCEON_API_KEY` | ⛔ 제외 | 수집 대상에서 제외된 소스입니다. 인증정보를 등록할 필요가 없습니다. |
| NKIS 국가정책연구포털 (`nkis`) | OPEN_API / API Key 필요 | `NKIS_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `NKIS_API_KEY` 설정 |
| 디지털집현전 (국가지식정보 통합플랫폼) (`kknowledge`) | OPEN_API / API Key 필요 | `KKNOWLEDGE_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `KKNOWLEDGE_API_KEY` 설정 |
| PRISM 정책연구관리시스템 (`prism`) | OPEN_API / API Key 필요 | `DATA_GO_KR_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `DATA_GO_KR_API_KEY` 설정 |
| 국가법령정보 공동활용 (`law_go_kr`) | OPEN_API / API Key 필요 | `LAW_GO_KR_OC` | ⬜ 조치 필요 | 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정 |
| 국회입법조사처 (`nars`) | OPEN_API / API Key 필요 | `ASSEMBLY_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `ASSEMBLY_API_KEY` 설정 |
| 한국형사·법무정책연구원 (`kicj`) | OPEN_API / API Key 필요 | `DATA_GO_KR_API_KEY` | ⬜ 조치 필요 | 공식 문서(https://www.data.go.kr/data/15140051/openapi.do)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력 |
| 국가인권위원회 (`humanrights`) | OPEN_API / API Key 필요 | `LAW_GO_KR_OC` | ⬜ 조치 필요 | 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정 |
| OpenAlex (`openalex`) | OPEN_API / API Key 필요 | `OPENALEX_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `OPENALEX_API_KEY` 설정 |
| Semantic Scholar (`semantic_scholar`) | OPEN_API / API Key 필요 | `SEMANTIC_SCHOLAR_API_KEY` | ✅ 완료 | 별도 발급 없이 사용 가능 |
| CORE (`core`) | OPEN_API / API Key 필요 | `CORE_API_KEY` | ⬜ 조치 필요 | 발급 후 `.env` 에 `CORE_API_KEY` 설정 |
| Unpaywall (`unpaywall`) | OPEN_API / 불필요 | `CONTACT_EMAIL` | ⬜ 조치 필요 | 발급 후 `.env` 에 `CONTACT_EMAIL` 설정 |
| Zenodo (`zenodo`) | OPEN_API / API Key 필요 | `ZENODO_API_KEY` | ✅ 완료 | 별도 발급 없이 사용 가능 |

## 2. 별도 발급 없이 사용 가능한 소스

- **사법정책연구원** (`jpri`) — 발급 불필요. **다만 endpoint 가 아직 비어 있어 수집되지 않습니다** — 공식 피드 주소 확인 필요
- **법무연수원** (`ioj`) — 발급 불필요. **다만 endpoint 가 아직 비어 있어 수집되지 않습니다** — 공식 피드 주소 확인 필요
- **한국국방연구원 (KIDA)** (`kida`) — 발급 불필요. **다만 endpoint 가 아직 비어 있어 수집되지 않습니다** — 공식 피드 주소 확인 필요
- **Crossref** (`crossref`) — 발급 불필요 (연락 이메일 `CONTACT_EMAIL` 권장) — 바로 사용 가능
- **DOAJ** (`doaj`) — 발급 불필요 — 바로 사용 가능
- **arXiv** (`arxiv`) — 발급 불필요 — 바로 사용 가능
- **SSRN** (`ssrn`) — 발급 불필요. 다만 자동수집 대상이 아니므로(공식 피드/API 없음 확인) 링크 보존만 합니다

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

- **조치 현황: ⛔ 제외** — 수집 대상에서 제외된 소스입니다. 인증정보를 등록할 필요가 없습니다.
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `SCIENCEON_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://scienceon.kisti.re.kr/apigateway/api/way/service/arti/serviceArtiSearchApi.do (2026-08-22, 공식 문서 검색결과 기준)

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | ScienceON (KISTI) |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://scienceon.kisti.re.kr/apigateway/api/main/mainForm.do |
| 5. 계정 생성 필요 여부 | 해당 없음 — 2026-08-23 수집 대상에서 제외 |
| 6. 신청 메뉴 경로 | 해당 없음 |
| 7. 서비스 목적 예시 | (수집 대상 제외) |
| 8. 승인 절차 | 해당 없음 |
| 9. 무료/유료 및 쿼터 | 해당 없음 |
| 10. OAuth Scope/권한 | 해당 없음 |
| 11. Redirect URI 필요 여부 | 해당 없음 |
| 12. 환경변수명 | `SCIENCEON_API_KEY` |
| 13. 동작 확인 방법 | `해당 없음 (enabled: false)` |
| 14. 키 만료·갱신·회수 | 해당 없음 |
| 15. 이용약관·자동수집 주의사항 | **2026-08-23 수집 대상에서 제외했습니다.** ScienceON API Gateway 는 이용신청 때 제출한 맥주소에 인증을 묶습니다. 토큰 발급 요청은 {mac_address, 현재일시} JSON 을 32자리 인증키로 AES256 암호화해 client_id 와 함께 보내고, Gateway 가 복호화해 등록된 맥주소와 대조한 뒤에야 토큰을 내줍니다. GitHub Actions 러너는 실행마다 맥주소가 달라져 등록값과 영구히 불일치하므로 이 구성에서는 사용할 수 없습니다. 되살리려면 (1) 고정 맥주소 서버로 이용신청, (2) 토큰 발급 절차(AES256 암호화·만료 시 재발급) 구현, (3) sources.yaml 의 enabled: true 가 모두 필요합니다. 근거: https://scienceon.kisti.re.kr/apigateway/api/way/guide/tokenGuide.do |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://apigateway.kisti.re.kr/openapicall.do`

**수집 정책**: `download_policy: oa_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

---

### NKIS 국가정책연구포털 (`nkis`)

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `NKIS_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `NKIS_API_KEY` / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://www.nkis.re.kr/openSvcList.do (2026-08-23, 운영자가 직접 입력 (공식 문서 대조 전))

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
| 15. 이용약관·자동수집 주의사항 | 엔드포인트는 운영자가 openSvcList.do 에서 확인해 입력했습니다(https://nkis.re.kr/nkisApi/search/TongList.do). 공식 문서를 직접 대조하지는 못했으므로 PENDING_VERIFICATION 상태입니다. request/field_map 은 아직 공공데이터포털 표준 형식 기본값이라 실제 요청인자·응답 필드명과 다르면 0건이 나올 수 있습니다. `python main.py doctor --probe` 로 확인하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://nkis.re.kr/nkisApi/search/TongList.do`

**수집 정책**: `download_policy: allowed` / `robots_policy: respect` / `rate_limit_rps: 0.5`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: OPEN_API

---

### 디지털집현전 (국가지식정보 통합플랫폼) (`kknowledge`)

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `KKNOWLEDGE_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `KKNOWLEDGE_API_KEY` / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://metadash.k-knowledge.kr/openApiService/apisso/business (2026-08-23, 운영자가 직접 입력 (공식 문서 대조 전))

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 디지털집현전 (국가지식정보 통합플랫폼) |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://metadash.k-knowledge.kr/openApiService/apisso/business |
| 5. 계정 생성 필요 여부 | 예 (디지털집현전 회원가입) |
| 6. 신청 메뉴 경로 | 디지털집현전(k-knowledge.kr) 회원가입 → 메타데이터 대시보드(metadash.k-knowledge.kr) → Open API 서비스 신청 → 사업자/기관 정보 입력 후 신청. 연계 안내는 k-knowledge.kr/m/guide/nkiLink.jsp |
| 7. 서비스 목적 예시 | 국가기관·지자체·공공기관이 생산한 국방·법률·정책 지식정보의 통합 메타데이터 수집 및 내부 리서치 색인 구축 |
| 8. 승인 절차 | 운영기관 검토 후 승인 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 제공 API 2종 — (1) 국가지식정보 메타데이터 제공 API, (2) 디지털집현전 보유 국가지식정보 검색 API. 이 시스템은 (2)를 사용합니다. |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `KKNOWLEDGE_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source kknowledge --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 검색 API 주소(https://metalink.k-knowledge.kr/search/openapi/search)는 운영자가 직접 입력했습니다. 요청인자·응답 필드명은 승인 후 발급되는 명세에만 담기므로 아직 기본값(공공데이터포털 표준 형식)이며, 실제 명세와 다르면 호출은 되어도 0건이 나옵니다. 명세를 받으면 config/sources.yaml 의 request/field_map 을 맞추고 `python main.py doctor --probe` 로 확인하십시오. 여러 기관 자료를 모으는 집계 플랫폼이라 KCI·NKIS·법령정보와 자료가 겹칠 수 있으나 다단계 중복제거가 처리합니다. 원문은 원 기관 사이트에 있으므로 기본 정책은 link_only 이며, 기관별 이용조건 확인 후에만 다운로드로 전환하십시오. |
| 16. 공식 문서 최종 확인일 | 2026-08-23 |

**설정된 엔드포인트**
  - `https://metalink.k-knowledge.kr/search/openapi/search`

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 0.5`

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

- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `ASSEMBLY_API_KEY` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `ASSEMBLY_API_KEY` / 확인상태: `VERIFIED`
  - 확인근거: https://open.assembly.go.kr/portal/openapi/openApiDevPage.do (2026-08-23, 운영자가 직접 입력 (공식 문서 대조 전))

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국회입법조사처 |
| 2. 사용 API/인증방식 | OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://open.assembly.go.kr/portal/openapi/openApiDevPage.do |
| 5. 계정 생성 필요 여부 | 예 (열린국회정보 회원가입) |
| 6. 신청 메뉴 경로 | 열린국회정보(open.assembly.go.kr) → 회원가입 → 인증키 신청. 계정당 최대 10개까지 발급받아 용도별로 나눠 쓸 수 있습니다. |
| 7. 서비스 목적 예시 | 국회입법조사처 연구보고서·발간물의 정기 수집 |
| 8. 승인 절차 | 공식 문서 확인 필요 |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 해당 없음 (API Key 방식) |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `ASSEMBLY_API_KEY` |
| 13. 동작 확인 방법 | `python main.py run --daily --source nars --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | **인증키가 공공데이터포털 키와 다릅니다.** 열린국회정보 전용 키를 발급받아 ASSEMBLY_API_KEY 로 등록하고, KEY 파라미터로 전달합니다. 제공 자료는 NARS 현안분석 보고서 목록입니다(2026-08-23 기준 753건, 최신순). 응답 필드는 BOOKNM(제목)·PDFFILEURL(원문 PDF)·VIEWERURL(뷰어)·INSERTDT(등록일) 네 개뿐이며 저자·초록·문서유형은 제공되지 않습니다. 목록에 ID 필드가 없어 PDF URL 의 doc_id 를 식별자로 씁니다. 검색어 파라미터가 없어 목록 전체를 받아 기간·주제로 거릅니다. VIEWERURL 은 DRM 뷰어(http, 포트 7003)라 링크 검증이 실패할 수 있으며 원문 확보는 PDFFILEURL 로 합니다. 공공데이터포털 경로는 2026-08-23 기준 활용신청 미승인(SERVICE_KEY_IS_NOT_REGISTERED_ERROR)이라 대체 경로로만 기록했습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-23 |

**설정된 엔드포인트**
  - `https://open.assembly.go.kr/portal/openapi/nvkfeqbsacvlzjmea`

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.5`

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
| 15. 이용약관·자동수집 주의사항 | 공식 RSS 는 확인되지 않았습니다. 발간자료(연구보고서·외국사법제도연구·학술행사자료)는 게시판(postList.do)으로 제공되므로, 자동수집 전 robots.txt 와 이용약관을 확인하고 허용되는 경우에만 전용 Adapter 를 구성하십시오. 참고: 대법원 사법정보공유포털(openapi.scourt.go.kr)이 연계 API 를 제공하지만 제공 범위가 사건기본정보·사건진행내용이어서 발간물 수집에는 쓸 수 없습니다. 2026-08-23 재확인 결과 공식 RSS·API 모두 확인되지 않았습니다. 당분간 연구보고서는 NKIS·디지털집현전 집계 경로로 유입되는지 확인하십시오. |
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
| 15. 이용약관·자동수집 주의사항 | 2026-08-23 재확인. 공식 RSS·오픈API 모두 확인되지 않았습니다. 발간물은 법무연수원 전자도서관(book.ioj.go.kr)에서 제공되며, 전자도서관 솔루션이 RSS 를 제공하는지는 신착자료(contents/new) 페이지에서 직접 확인해야 합니다. 확인 전까지는 자동수집하지 않습니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - (미설정)

**수집 정책**: `download_policy: manual_review` / `robots_policy: respect` / `rate_limit_rps: 0.3`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS

---

### 한국형사·법무정책연구원 (`kicj`)

- **조치 현황: ⬜ 조치 필요** — 공식 문서(https://www.kicj.re.kr/)에서 상세주소를 확인해 `config/sources.yaml` 의 `endpoint` 에 입력
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
| 15. 이용약관·자동수집 주의사항 | 2026-08-23 재확인. 기관 자체 RSS 는 확인되지 않았고, 공공데이터포털의 KICJ 데이터셋(15140051 교정통계연보 / 15140052 범죄예방정책)은 모두 통계라 연구보고서 수집에는 쓸 수 없습니다. 연구보고서 원문은 기관 홈페이지 발간물 게시판(board.es?mid=a10101000000&bid=0001)에서 제공되므로, 자동수집이 필요하면 robots.txt·이용약관 확인 후 전용 Adapter 를 구성해야 합니다. 그 전까지는 NKIS·디지털집현전 집계 경로로 들어오는지 확인하십시오. |
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
- **조치 현황: ⬜ 조치 필요** — 발급 후 `.env` 에 `LAW_GO_KR_OC` 설정
- **OPEN_API** — 인증: API Key 필요 / 사전 발급 필요: 예 / 환경변수: `LAW_GO_KR_OC` / 확인상태: `PENDING_VERIFICATION`
  - 확인근거: https://open.law.go.kr/LSO/openApi/guideList.do (2026-08-23, 운영자가 직접 입력 (공식 문서 대조 전))

| 항목 | 내용 |
| --- | --- |
| 1. 서비스/기관명 | 국가인권위원회 |
| 2. 사용 API/인증방식 | RSS(불필요), OPEN_API(API Key 필요) |
| 3. 사전 발급 필요 여부 | 예 |
| 4. 공식 발급/신청 페이지 | https://open.law.go.kr/LSO/openApi/guideList.do |
| 5. 계정 생성 필요 여부 | 예 (국가법령정보 공동활용 신청 시 부여되는 OC) |
| 6. 신청 메뉴 경로 | 국가법령정보 공동활용 → 오픈API 신청. law_go_kr 과 같은 OC 를 사용하므로 이미 발급받았다면 추가 발급은 필요 없습니다. |
| 7. 서비스 목적 예시 | 국가인권위원회 진정사건 결정문의 정기 수집 및 인권·군사법 쟁점 추적 |
| 8. 승인 절차 | 신청 후 승인 (승인 시 OC 식별자 부여) |
| 9. 무료/유료 및 쿼터 | 공식 문서 확인 필요 |
| 10. OAuth Scope/권한 | 신청 범위에 위원회 결정문이 포함되는지 확인이 필요할 수 있습니다. |
| 11. Redirect URI 필요 여부 | 불필요 |
| 12. 환경변수명 | `LAW_GO_KR_OC` |
| 13. 동작 확인 방법 | `python main.py run --daily --source humanrights --dry-run` |
| 14. 키 만료·갱신·회수 | 공식 문서 확인 필요 |
| 15. 이용약관·자동수집 주의사항 | 결정문은 위원회가 아니라 법제처가 개방합니다. 운영자가 확인한 target 코드는 nhrck 이며, 요청 형태는 https://www.law.go.kr/DRF/lawSearch.do?OC=<OC>&target=nhrck&type=XML 입니다. 응답 필드명은 아직 대조하지 못했습니다 — 제목을 읽지 못하면 Connector 가 실제 응답 필드 목록을 경고 로그로 남기므로, 그 값을 보고 law_openapi 의 TARGET_META 를 보완하십시오. 발간물·연구보고서는 인권도서관(library.humanrights.go.kr)에 있으며 공식 RSS 가 확인되지 않아 아직 수집하지 않습니다. 한 소스는 Connector 하나만 쓰므로, RSS 주소를 찾으면 별도 소스로 분리해야 합니다. |
| 16. 공식 문서 최종 확인일 | 2026-08-22 |

**설정된 엔드포인트**
  - `https://www.law.go.kr/DRF/lawSearch.do`

**수집 정책**: `download_policy: link_only` / `robots_policy: respect` / `rate_limit_rps: 1.0`

> ⚠ **구현 직전 재확인 필요** — 아래 접근방식은 공식 문서로 확정되지 않았습니다: RSS, OPEN_API

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
| 15. 이용약관·자동수집 주의사항 | 2026-08-23 재확인. 공식 RSS 주소는 확인되지 않았습니다. 기관 홈페이지의 '공공데이터 소개'(sidx=2127) 페이지는 국내외 국방·안보 데이터 목록과 학술지 목록을 개방한다고 안내하지만, 오픈API 목록·상세주소는 공개 검색으로 확인되지 않았습니다. 해당 페이지에서 제공 형식과 이용조건을 확인한 뒤 endpoint 를 입력하십시오. |
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
| 16. 공식 문서 확인일 | `2026-08-24` |

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
| `SCIENCEON_API_KEY` | ScienceON (KISTI) OPEN_API 인증 | 불필요 (수집 대상 제외) |
| `NKIS_API_KEY` | NKIS 국가정책연구포털 OPEN_API 인증 | 필수 |
| `KKNOWLEDGE_API_KEY` | 디지털집현전 (국가지식정보 통합플랫폼) OPEN_API 인증 | 필수 |
| `DATA_GO_KR_API_KEY` | PRISM 정책연구관리시스템 OPEN_API 인증 | 필수 |
| `LAW_GO_KR_OC` | 국가법령정보 공동활용 OPEN_API 인증 | 필수 |
| `ASSEMBLY_API_KEY` | 국회입법조사처 OPEN_API 인증 | 필수 |
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


## 부록 D. 정기 수집을 GitHub Actions 로 돌리는 경우

`credential-check.yml` 은 **점검 전용**이며 자료를 수집하지 않습니다.
GitHub Actions 에서 정기 수집까지 돌리려면 아래를 고려하십시오.

### D-1. 먼저 판단해야 할 것

| 항목 | 확인 사항 |
| --- | --- |
| 수집 파일 보관 | Actions 러너는 **실행이 끝나면 사라집니다.** `data/library/` 를 artifact 로 올리거나 외부 저장소에 커밋·업로드해야 유지됩니다. |
| SQLite 상태 | 중복 판별·증분 수집은 `data/metadata/dlrcis.db` 의 이력에 의존합니다. DB 를 매 실행마다 복원·저장하지 않으면 **매번 최초 실행처럼 동작**합니다. |
| 저작권 | 수집한 원문을 공개 저장소에 커밋하면 재배포가 됩니다. 라이선스가 불명확한 자료는 커밋하지 마십시오 (PRD §18.5). |
| 실행 시간 | Actions 작업에는 시간 제한이 있습니다. 백필처럼 오래 걸리는 작업은 로컬·서버 실행이 적합합니다. |

> 위 제약 때문에 **정기 수집은 사내 서버나 개인 PC 에서 `.env` + OS 스케줄러로 운영**하고,
> GitHub Actions 는 점검·테스트 용도로만 쓰는 구성을 권장합니다.
> Windows 는 `scripts/setup_scheduler.bat` 로 등록할 수 있습니다.

### D-2. 그래도 Actions 로 돌린다면

`.github/workflows/daily-collection.yml` 을 만들고
`credential-check.yml` 의 `env:` 블록을 그대로 복사한 뒤 아래를 참고하십시오.

```yaml
on:
  schedule:
    # UTC 기준입니다. KST 07:30 = UTC 22:30 (전날)
    - cron: "30 22 * * *"
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest
    env:
      # credential-check.yml 의 env 블록을 그대로 복사
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt

      # 이전 실행의 DB 를 복원해야 증분 수집·중복 판별이 동작합니다.
      - uses: actions/cache@v4
        with:
          path: data/metadata
          key: dlrcis-db-${{ github.run_id }}
          restore-keys: dlrcis-db-

      - run: python main.py run --daily

      - uses: actions/upload-artifact@v4
        with:
          name: 수집결과
          path: |
            data/manifests/
            data/metadata/list_download_resources.xlsx
```

> `data/library/` (원문 파일)는 위 예시에서 **업로드하지 않습니다.**
> 저작권·라이선스를 검토한 뒤 보관 위치를 직접 정하십시오.


> 마지막 생성: 2026-08-24 · `python main.py api-guide` 로 재생성할 수 있습니다.
