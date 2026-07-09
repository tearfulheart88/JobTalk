# 진로톡(CareerTalk) 개발 현황 (STATUS)

> 이 파일을 매 작업 시작 시 먼저 읽고, 작업 끝에 갱신할 것. 새 폴더 만들지 말고 이 루트에서만 작업.
> 최종 갱신: 2026-07-02 (P0 라이브 방어 4종 + P1 품질 5종 완료)

## 현재 상태 — MVP 동작 (Mock) ✅ + 서버 기동 검증 완료 ✅ + P0·P1 개선 완료 ✅
- 기획서: `AGENTIC_PLAYER10_진로톡_기획서_v2.md` — 완료
- 코드(`careertalk/`): 4개 Tool 구현 완료, **Mock 통합 테스트 32/32 통과**
  - `server.py` — FastMCP 엔트리포인트 (4 Tool + status 리소스). 기본 포트 8001.
  - `tools/common.py` — 환경변수·LLM 클라이언트·**Prompt Caching**·**Response Cache**·Mock 판별
  - `tools/formatters.py` — **Kakao 카드 포매터**(진로/공고/정책/코칭)
  - `tools/search_jobs.py` — 사람인 OpenAPI (+캐시, +카드)
  - `tools/analyze_job_fit.py` — LLM 진로분석 (+캐시, +진로카드)
  - `tools/search_youth_policies.py` — 온통청년 **v2 getPlcy + 구버전** 동시 지원 (+캐시, +정책카드)
  - `tools/generate_resume_tip.py` — LLM 자소서첨삭 (+캐시, +코칭카드)
  - `README.md`, `requirements.txt`, `.env.example`
  - `tests/test_servers.py` — 23 케이스 (Windows cp949 출력, JSON 파서, 입력 보정, 캐시 제한, 외부 파서 방어 검증)

## 2026-07-02 P1 품질 개선 (P0 직후 같은 날)
- **청년정책 페이지네이션 정합**: 나이·지역·상황 후처리 필터로 결과가 줄면 display 를 채울 때까지 다음 페이지를 이어서 조회(`YOUTH_MAX_FETCH_PAGES` 기본 3). 응답에 `fetched_pages`, `api_total`(필터 전 전체 건수), `has_more` 추가. 후속 페이지 오류·레이트리밋 시 부분 결과 반환. 수집 로직은 `_collect_filtered` 로 분리(테스트 가능).
- **D-day KST 고정**: `formatters._dday` 가 서버 로컬이 아닌 KST(UTC+9 고정, DST 없음) 자정 기준으로 계산. UTC 클라우드 배포 시 하루 어긋나던 문제 해소.
- **Mock 키워드 토큰 매칭**: "프론트엔드 React" 같은 다단어 검색도 토큰 단위로 매칭(매칭 수 내림차순 정렬).
- **.env 탐색 범위 축소**: 상위 4단계 → 프로젝트 루트·실행 위치·서버 폴더만. 무관한 상위 폴더 .env 혼입 방지.
- **server.py 래퍼 중복 제거**: 시그니처·docstring 을 복사하던 4개 래퍼 삭제, `mcp.tool()(fn)` 직접 등록. tools/ 모듈이 단일 소스.
- **검증**: compileall 통과, `python tests/test_servers.py` → **32/32 passed** (D-day KST 1 + 토큰 매칭 1 + 페이지 수집 3 추가), Mock 서버 기동 + MCP tools/list 4개 도구 + 실호출 확인.
- 주의(라이브 검증 시): 다중 페이지 조회는 온통청년 실 API 에서만 동작 경로 — 키 확보 후 `fetched_pages`>1 케이스 실측 필요.

## 2026-07-02 P0 라이브 방어 (공개 배포 전 필수 수정)
- **async LLM + 타임아웃**: `call_llm` 을 `AsyncOpenAI` 기반 async 로 전환(`await` 필요). 동기 호출이 이벤트 루프를 막던 문제 해소. `LLM_TIMEOUT_SECONDS`(기본 30초) + `max_retries=1`.
- **LLM 파싱 실패 미캐시**: `analyze_job_fit`·`generate_resume_tip` 에서 JSON 파싱 실패 응답은 캐시하지 않음(성공만 캐시). 일시 오류가 TTL 동안 고착되던 문제 해소. 테스트로 검증.
- **로깅 도입**: `logging` 전면 적용 — LLM 폴백 원인, 사람인/온통청년 HTTP 오류, 레이트리밋 초과가 WARNING 으로 남음. `server.py` 에서 `basicConfig`(LOG_LEVEL, 기본 INFO).
- **레이트리미터**: 프로세스 전역 슬라이딩 윈도우(60초). scope 분리 — `llm`(기본 10회/분, `LLM_RATE_LIMIT_PER_MINUTE`) / `external`(기본 30회/분, `RATE_LIMIT_PER_MINUTE`). Mock 모드 자동 비활성, `RATE_LIMIT_ENABLED=false` 로 해제. 캐시 히트는 카운트 안 함(외부 호출 직전에만 검사). 초과 시 일관된 error 스키마 반환.
- **개인정보 고지**: `generate_resume_tip` 라이브 응답에 `privacy_notice`(자소서가 OpenAI 로 전송됨) 필드 추가.
- **.env.example**: `LLM_TIMEOUT_SECONDS`, `RATE_LIMIT_*`, `LOG_LEVEL` 문서화.
- **검증**: compileall 통과, `python tests/test_servers.py` → **27/27 passed** (레이트리미터 2 + 실패미캐시 2 추가), Mock 서버 기동 + MCP tools/list + 4개 도구 호출 확인.
- 주의: 레이트리밋은 프로세스 전역(클라이언트 IP 단위 아님 — MCP 도구 시점엔 IP 를 모름). IP 단위가 필요하면 배포 시 리버스 프록시에서 처리.

## 2026-06-27 운영 안정성 개선
- **환경변수 우선순위 정리**: `.env` → `.env.local` 순서와 프로젝트 전용 설정 우선순위를 명확히 하고, 실제 프로세스 환경변수는 파일보다 우선하도록 보장.
- **LLM provider 캐시 제거**: 런타임 중 환경변수가 바뀌어도 OpenAI 키 상태를 즉시 반영.
- **응답 캐시 강화**: 캐시 키를 JSON 기반으로 안정화하고 `RESPONSE_CACHE_MAX_ENTRIES`(기본 256) 초과 시 오래된 항목을 제거. TTL 0 이하에서는 저장하지 않음.
- **사람인 API 방어 파서**: 실제 응답 필드가 문자열/객체로 흔들려도 서버가 예외로 죽지 않도록 `_as_dict`, `_field_name`, `_safe_int` 추가. API 오류 응답도 `kakao_cards`, `source`, `message`를 포함하는 일관 스키마로 반환.
- **온통청년 API 안정화**: `YOUTH_API_ENDPOINT`를 호출 시점에 동적으로 읽고, Mock 응답에도 나이·지역·상황 필터 적용. API 오류 응답 스키마 일관화.
- **필수 입력 가드**: `analyze_job_fit(interests="")`, `generate_resume_tip(resume_text=None)` 같은 입력에서 예외 대신 명확한 `error` 반환.
- **서버 모드 표시 개선**: 키 일부만 설정된 상태는 `mixed`, 전부 없음은 `mock`, 전부 설정은 `live`로 표시.
- **검증 완료**:
  - `python -m compileall careertalk tests` 통과
  - `python tests/test_servers.py` → **23/23 passed**
  - MCP streamable-http 클라이언트로 `http://127.0.0.1:8013/mcp` 초기화 + `tools/list` 확인

## 2026-06-24 실행 안정화
- **Windows 콘솔 기동 오류 수정**: `server.py` 시작 로그의 `✓/✗` 문자가 cp949 출력에서 `UnicodeEncodeError`를 내던 문제 제거. stdout/stderr UTF-8 재설정 + ASCII 상태 라벨 사용.
- **CLI 실행 지원**: `python server.py --mock --port 8001`처럼 바로 실행 가능. `--host`, `--port`, `--transport`, `--mock` 지원.
- **Windows 런처 추가**: 프로젝트 루트 `start-careertalk.bat` 추가. Mock 서버가 8001 포트로 시작.
- **환경변수 로딩 강화**: 실행 위치가 달라도 `careertalk/.env`, 상위 폴더 `.env`, `.env.local`을 안정적으로 읽음.
- **LLM 폴백 강화**: OpenAI 호출 실패 시 서버가 죽지 않고 Mock 결과로 폴백. JSON 모드 우선 사용 + 설명문이 섞인 JSON 응답도 추출.
- **외부 API 입력 보정**: 잘못된 숫자형 `count`, `start`, `display`, `page_index` 입력을 안전한 기본값으로 보정.
- **사람인 마감일 정규화**: `YYYYMMDD`, Unix timestamp 형식도 `YYYY-MM-DD`로 변환해 Kakao 카드 D-day 계산 가능.
- **온통청년 후처리 필터**: 실제 API 응답을 나이·지역·상황 조건으로 한 번 더 좁힘.
- **검증 완료**:
  - `python -m compileall careertalk tests` 통과
  - `python tests/test_servers.py` → **20/20 passed**
  - `python server.py --mock --port 8011` 실제 포트 바인딩 확인
  - MCP streamable-http 클라이언트로 `http://127.0.0.1:8012/mcp` 초기화 + `tools/list` 확인

## 2026-06-23 Anthropic 제거·OpenAI 단일화
- **이유**: MCP 서버는 도구를 제공하는 서버일 뿐, 내부에서 어떤 LLM API를 쓰든 자유. 두 개를 지원할 필요 없음.
- **변경**: `common.py`에서 Anthropic provider·`get_anthropic_key()`·`cache_control` 코드 제거, OpenAI 단일 구조로 단순화
- `requirements.txt`에서 `anthropic` 제거
- `.env.example`에서 `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` 제거
- `README.md` 기술스택·환경변수표·LLM 발급 가이드 OpenAI만 남김
- `server.py` status 리소스 features 문구 수정
- 17/17 테스트 재검증 통과

## 2026-06-23 서버 기동 검증 결과 ✅
- **서버 기동**: `MOCK_MODE=true MCP_PORT=8001 python server.py` → 정상 기동
- **MCP 핸드셰이크**: initialize 요청 → `CareerTalk` 서버 정보 정상 반환
- **tools/list**: 4개 도구(search_jobs, analyze_job_fit, search_youth_policies, generate_resume_tip) 정상 등록
- **Tool 1 search_jobs**: Mock 3건(백엔드/프론트엔드/데브옵스) + kakao_cards 3장 정상 반환
- **Tool 2 analyze_job_fit**: 추천 직무 5개 + kakao_cards 정상 반환
- **Tool 3 search_youth_policies**: Mock 정책 3건 + kakao_cards 정상 반환
- **Tool 4 generate_resume_tip**: 첨삭 + 개선점 3개 + kakao_cards 2장 정상 반환
- **Resource careertalk://status**: 모드·키 상태·기능 목록 정상 반환
- **의존성**: mcp 1.26.0, httpx 0.28.1, openai 2.24.0, uvicorn 0.41.0, python-dotenv 1.2.2 설치됨

## 2026-06-22 개선 내역
1. **Prompt Caching** — 도구 고정 시스템 프롬프트 프리픽스 캐싱(OpenAI 자동). 기획서 §2.3 핵심 기능.
2. **Response Cache** — 동일 입력 TTL 캐시(사람인 일일 500회 한도 보호·LLM 비용 절감), Mock 모드 자동 비활성.
3. **Kakao 카드 위젯** — 4개 도구 모두 `kakao_cards` 반환(기획서 §3.4). 채널 메시지/알림톡 템플릿에 1:1 매핑되는 렌더러 중립 스키마.
4. **온통청년 API 정합성** — 구버전(`youthPlcyList.do`/`openApiVlak`) 추정 코드를 현행 v2(`getPlcy`/`apiKeyNm`/`pageNum`/`pageSize`) 기본으로 교정 + 두 응답 형식 모두 파싱 + `YOUTH_API_ENDPOINT` 로 전환 가능.
5. **모델 교정** — `.env.example` 의 LLM 설정을 OpenAI 기본 모델(`gpt-4o-mini`) 기준으로 정리.
6. **테스트 인코딩** — Windows 콘솔(cp949)에서 ✓/✗·한글이 깨지던 문제 해결(stdout UTF-8 재설정).
7. **오타** — `SMA 운영`→`SNS 운영`, `증빌`→`증빙`.

## 다음 할 일
0. **P2 백로그** — 멀티 소스 채용검색(provider 구조 + 워크넷/고용24 API 추가), pytest 이관, requirements 상한 고정, `mentor_connect`(기획서 선택 기능). ~~P1 5종~~ → 2026-07-02 완료.
1. **라이브 검증(키 필요)** — 사람인 access-key / 온통청년 인증키 / OpenAI 키로 실제 호출 점검.
   - 온통청년 키가 구버전이면 `.env` `YOUTH_API_ENDPOINT` 를 legacy 로 교체.
   - `careertalk://status` 리소스로 모드·키 상태 확인.
2. **PlayMCP 등록** — 공개 HTTPS 엔드포인트 배포 후 등록 (README §PlayMCP).
3. (여유 시) `mentor_connect` 추가 — 기획서상 선택 기능.

## 규칙 리마인더
- 소스는 write_file로만. chcp 등 Windows 명령 금지(bash 환경). .venv를 폴더 안에 만들지 말 것.
- 막히거나 턴이 길어지면 여기 STATUS를 갱신하고 멈춘 뒤 "/new 후 이어가기" 안내.
- 검증: `python tests/test_servers.py` (Mock), 각 .py `python -c "import ast; ast.parse(...)"`.
