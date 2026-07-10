# JobTalk / 진로톡

청년의 진로 탐색, 채용공고·청년정책 검색, 자기소개서 코칭을 제공하는 한국어 MCP 서버입니다.
AGENTIC PLAYER 10 출품을 위한 검증 가능한 프로토타입입니다.

## 구현 상태

- 공식 MCP Python SDK `FastMCP`
- stateless Streamable HTTP + JSON response
- MCP endpoint: `/mcp`
- health endpoint: `/health`
- 통합·회귀 테스트 32개 통과
- 공식 MCP 클라이언트 initialize, tools/list, tools/call 통과
- 외부 API 키가 없을 때 명확히 표시된 데모 데이터 제공

## MCP Tools

| Tool | 기능 | 실제 연동 |
|---|---|---|
| `search_jobs` | 키워드·지역·직무·학력 기반 채용 검색 | 사람인 OpenAPI |
| `analyze_job_fit` | 관심·학력·성향 기반 직무 TOP 5와 진입 경로 | OpenAI |
| `search_youth_policies` | 나이·지역·상황 기반 청년정책 검색 | 온통청년 OpenAPI |
| `generate_resume_tip` | 자기소개서 첨삭과 예상 면접질문 | OpenAI |

모든 Tool은 원본 결과와 함께 카카오 카드로 변환하기 쉬운 `kakao_cards`를 반환합니다.

## 빠른 시작

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
cd careertalk
python server.py --mock --host 127.0.0.1 --port 8001
```

확인 주소:

- 상태: `http://127.0.0.1:8001/health`
- MCP: `http://127.0.0.1:8001/mcp`

## API 설정

`careertalk/.env.example`을 참고해 로컬 `.env` 또는 배포 환경변수에 설정합니다.

```dotenv
SARAMIN_ACCESS_KEY=
YOUTH_OPEN_API_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
MOCK_MODE=false
```

- 사람인: 공식 `https://oapi.saramin.co.kr/job-search`
- 온통청년: 공식 공개 문서의 `https://www.youthcenter.go.kr/opi/youthPlcyList.do`
- OpenAI: 진로 분석과 자기소개서 코칭

키가 없거나 `MOCK_MODE=true`이면 데모 응답을 반환합니다. 데모 카드에는 `데모` 태그가
붙으며, 가짜 상세 주소 대신 사람인·온통청년 공식 검색 페이지로 연결됩니다. 마감일은 실행일
기준으로 생성해 오래된 데모가 실제 공고처럼 오인되지 않도록 했습니다.

자기소개서 원문은 OpenAI 연동 시 API로 전송됩니다. 서버가 영구 저장하지는 않지만 동일 입력
응답 캐시가 최대 1시간 유지될 수 있습니다. 캐시 키에는 원문 대신 SHA-256 해시만 저장합니다.
실제 주민번호, 계좌번호, 연락처 등 불필요한 개인정보는 입력하지 마세요.

## Docker / PlayMCP in KC

Git 소스 빌드 입력값:

- Git URL: `https://github.com/tearfulheart88/JobTalk`
- Branch/ref: `main`
- Dockerfile path: `Dockerfile`
- Endpoint path: `/mcp`

```powershell
docker build -t jobtalk .
docker run --rm -p 8001:8001 -e MOCK_MODE=true jobtalk
```

컨테이너는 non-root 사용자로 실행되고 `/health`를 점검합니다. 배포 플랫폼이 `PORT`를
주입하면 그 값을 사용하며, 없으면 8001 포트를 사용합니다.

세부 Tool 스키마와 환경변수는 [careertalk/README.md](careertalk/README.md)를 참고하세요.
