# CareerTalk MCP Server

> **청년 진로·취업 AI 멘토** — AGENTIC PLAYER 10 공모전 제출용 MCP 서버 MVP
>
 카카오톡 대화로 AI가 청년의 진로·취업 고민을 해결하는 진로톡(CareerTalk) 서버입니다.

## 제공 도구 (4종)

| 도구 | 기능 | 데이터 소스 |
|------|------|------------|
| `search_jobs` | 맞춤 채용공고 검색 | 사람인 OpenAPI (`oapi.saramin.co.kr`) |
| `analyze_job_fit` | AI 진로 적성 진단 및 직무 추천 | LLM (OpenAI GPT) |
| `search_youth_policies` | 청년정책·지원금 매칭 | 온통청년 OpenAPI (`youthcenter.go.kr`) |
| `generate_resume_tip` | 자기소개서 첨삭 + 면접 예상질문 생성 | LLM (OpenAI GPT) |

> 모든 도구는 결과에 **`kakao_cards`** (카드형 위젯 렌더링 데이터)를 함께 반환합니다.

## 성능·UX 기능 (기획서 §2.3 / §3.4 구현)

- **Prompt Caching** — OpenAI는 1024토큰 이상 동일 접두사를 자동 캐싱. 시스템 프롬프트를 맨 앞에 고정하는 것만으로 입력비용·TTFT 절감.
- **Response Cache** — 동일 입력 재요청은 외부 API·LLM 재호출 없이 즉시 반환(TTL). 사람인 일일 500회 한도 보호 + LLM 비용 절감. Mock 모드에선 자동 비활성.
- **Kakao 카드** — 진로/공고/정책/코칭 카드. 카카오 채널 메시지·알림톡 템플릿(basicCard/listCard)에 1:1 매핑되는 렌더러 중립 스키마.
- **온통청년 v2** — 현행 `getPlcy`(apiKeyNm) 기본 + 구버전 `youthPlcyList.do`(openApiVlak) 동시 지원, `YOUTH_API_ENDPOINT` 로 전환.

## 기술 스택

- **프레임워크**: Python + FastMCP (MCP Python SDK 1.26+)
- **전송**: streamable-http (PlayMCP 등록용)
- **HTTP 클라이언트**: httpx (비동기)
- **LLM**: OpenAI (gpt-4o-mini)
- **캐싱**: OpenAI 자동 프리픽스 캐싱 + Response Cache(동일 입력 TTL 캐시)
- **출력**: Kakao 카드(진로/공고/정책/코칭) 동시 반환 — 채널 메시지·알림톡 템플릿에 1:1 매핑

## 디렉토리 구조

```
careertalk/
├── server.py              # FastMCP 메인 서버 (4개 Tool 등록)
├── requirements.txt       # 의존성 목록
├── .env.example           # API 키 설정 템플릿
├── README.md              # 이 파일
└── tools/
    ├── __init__.py        # 도구 모듈 패키지
    ├── common.py          # 공통 유틸 (환경변수, LLM+Prompt Caching, 응답 캐시, Mock 판별)
    ├── formatters.py      # Kakao 카드 포매터 (진로/공고/정책/코칭)
    ├── search_jobs.py     # Tool 1: 사람인 채용공고 검색
    ├── analyze_job_fit.py # Tool 2: LLM 진로 적성 분석
    ├── search_youth_policies.py  # Tool 3: 온통청년 정책 검색 (v2 getPlcy + 구버전)
    └── generate_resume_tip.py    # Tool 4: LLM 자소서 첨삭
tests/
└── test_servers.py        # 통합 테스트 (17개 케이스)
```

## 설치 및 실행

### 1. 의존성 설치

```bash
cd careertalk
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example` 을 복사해 `.env` 를 만들고 API 키를 입력합니다.

```bash
cp .env.example .env
# .env 편집:
#   SARAMIN_ACCESS_KEY=...     (https://oapi.saramin.co.kr/ 에서 발급)
#   YOUTH_OPEN_API_KEY=...     (https://www.data.go.kr/data/15143273/openapi.do 에서 발급)
#   OPENAI_API_KEY=...         (진로 분석·자소서 첨삭에 사용)
```

> **API 키가 없어도 실행 가능** — Mock 모드로 샘플 데이터를 반환합니다.
> `.env` 에 `MOCK_MODE=true` 를 설정하거나, 실행 시 `--mock` 을 붙이면 됩니다.

### 3. 서버 실행

```bash
python server.py --mock --port 8001

# 실제 API 키를 쓸 때:
python server.py --port 8001

# 환경변수 방식도 지원:
MCP_PORT=8001 MOCK_MODE=true python server.py
```

Windows 에서는 프로젝트 루트의 `start-careertalk.bat` 으로 Mock 서버를 바로 실행할 수 있습니다.

기본 endpoint: `http://localhost:8001/mcp`

### 4. MCP Inspector 로 확인

```bash
npx @modelcontextprotocol/inspector
# → http://localhost:6274 접속 → http://localhost:8001/mcp 연결
```

## API 키 발급 가이드

### 사람인 OpenAPI

1. https://oapi.saramin.co.kr/ 방문
2. 회원가입 후 이용신청
3. 승인 후 access-key 발급 (1일 500회 제한)

### 온통청년 OpenAPI

1. https://www.data.go.kr/data/15143273/openapi.do 방문
2. 공공데이터포털 계정으로 활용신청
3. 인증키 발급 (무료, 제한 없음)
   - 현행 v2(`getPlcy`)는 `apiKeyNm`, 구버전(`youthPlcyList.do`)은 `openApiVlak` 사용
   - 발급키가 구버전이면 `.env` 의 `YOUTH_API_ENDPOINT` 를 legacy 로 교체

### LLM API

- OpenAI: https://platform.openai.com/api-keys

## Mock 모드 동작

API 키가 설정되지 않았거나 `MOCK_MODE=true` 인 경우:

| 도구 | Mock 동작 |
|------|-----------|
| `search_jobs` | 5건의 샘플 IT 공고 반환, 키워드 필터링 지원 |
| `analyze_job_fit` | IT/비IT 관심분야별 5개 추천 직무 반환 |
| `search_youth_policies` | 6건의 샘플 청년정책 반환, 지역 필터링 지원 |
| `generate_resume_tip` | 원문을 간단히 다듬은 첨삭본 + 5개 예상질문 반환 |

## 테스트

```bash
python tests/test_servers.py
```

17개 테스트 케이스 검증:
- server.py 임포트 + 4개 Tool 등록 확인
- search_jobs: 기본 검색, 키워드 필터, count 제한
- analyze_job_fit: IT/비IT 진로 분석
- search_youth_policies: 정책 검색, 지역 필터, display 제한
- generate_resume_tip: 자소서 첨삭, 빈 입력 처리
- kakao_cards: 공고/진로/정책/코칭 카드 렌더링
- response_cache: 캐시 키 안정성 + 저장/조회 + TTL 만료

> Windows 콘솔(cp949)에서도 깨지지 않도록 테스트가 stdout 을 UTF-8 로 재설정합니다.

## PlayMCP 등록 가이드

1. 서버를 공개 엔드포인트에 배포 (HTTPS 필수)
   - 카카오 클라우드, AWS, Fly.io 등
   - 예: `https://careertalk.example.com/mcp`
2. https://playmcp.kakao.com/ 접속 → 카카오 계정 로그인
3. "MCP 등록하기" 클릭
4. Remote MCP Server 선택 → 엔드포인트 URL 입력
5. 인증 방식 선택 (현재 MVP 는 인증 없음)
6. 등록 완료 → AI 채팅에서 도구 호출 확인

## 배포 예시 (Docker)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8001
CMD ["python", "server.py", "--port", "8001"]
```

```bash
docker build -t careertalk-mcp .
docker run -p 8001:8001 --env-file .env careertalk-mcp
```

## 환경변수 참조

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SARAMIN_ACCESS_KEY` | (없음) | 사람인 OpenAPI access-key |
| `YOUTH_OPEN_API_KEY` | (없음) | 온통청년 OpenAPI openApiVlak |
| `OPENAI_API_KEY` | (없음) | OpenAI API 키 (LLM) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI 모델명 |
| `MOCK_MODE` | `false` | true 시 외부 API 없이 샘플 데이터 반환 |
| `MCP_TRANSPORT` | `streamable-http` | MCP 전송 방식 |
| `MCP_HOST` | `0.0.0.0` | 서버 바인딩 호스트 |
| `MCP_PORT` | `8001` | 서버 포트 |
| `RESPONSE_CACHE_ENABLED` | `true` | 동일 입력 TTL 캐시 (Mock 모드 자동 비활성) |
| `JOBS_CACHE_TTL` | `600` | 사람인 결과 캐시 (초) |
| `YOUTH_CACHE_TTL` | `600` | 온통청년 결과 캐시 (초) |
| `LLM_CACHE_TTL` | `3600` | LLM 결과 캐시 (초) |
| `YOUTH_API_ENDPOINT` | `…/go/ythip/getPlcy` | 온통청년 엔드포인트 (기본 현행 v2) |

## 라이선스

AGENTIC PLAYER 10 공모전 제출용 MVP.
