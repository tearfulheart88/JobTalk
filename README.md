# JobTalk / 진로톡

청년의 진로 탐색, 채용공고·청년정책 검색, 자기소개서 코칭을 제공하는 한국어 MCP 서버입니다.
AGENTIC PLAYER 10 출품을 위한 검증 가능한 프로토타입입니다.

> **정보를 더 주는 서비스가 아니라, 막막함을 오늘의 행동으로 바꾸는 커리어 실행 도구입니다.**

심사위원용 대표 질문과 구현 경계는 [SUBMISSION.md](SUBMISSION.md)에 30초 분량으로 정리했습니다.

## 대표 경험

처음 실행하면 목적, 사용법, 안전한 입력 범위와 다섯 가지 시작 예시를 버튼으로 보여줍니다.
목표를 길게 설명하지 않아도 `7일 계획 시작`, `맞는 직무 찾기`, `청년정책 찾기` 중 하나로 시작할 수 있습니다.

`"백엔드 개발자로 취업하고 싶은데 알바 때문에 하루 20분밖에 없고 경력도 없어요"`라고 물으면
진로톡은 오늘의 최소 행동, 완료 기준, 막혔을 때의 축소 행동과 7일 실행계획을 먼저 제시합니다.
이후 채용공고·청년정책·직무분석·자소서 첨삭으로 자연스럽게 이어집니다.

## 구현 상태

- 공식 MCP Python SDK `FastMCP`
- stateless Streamable HTTP + JSON response
- MCP endpoint: `/mcp`
- health endpoint: `/health`
- pytest 22개, 통합·회귀 검증 41개 통과
- 공식 MCP 클라이언트 initialize, tools/list, tools/call 통과
- 외부 API 키가 없을 때 명확히 표시된 데모 데이터 제공
- PlayMCP 필수 Tool annotations 5개를 6개 Tool에 모두 명시
- SQLite 일일 한도, 분당·동시 호출 제한, 2.5초 타임아웃 상한 적용

## MCP Tools

| Tool | 기능 | 실제 연동 |
|---|---|---|
| `career_guide` | 첫 사용 안내·예시·FAQ·개인정보 원칙 | 외부 API 없음 |
| `search_jobs` | 키워드·지역·직무·학력 기반 채용 검색 | 사람인 OpenAPI |
| `analyze_job_fit` | 관심·학력·성향 기반 직무 TOP 5와 진입 경로 | OpenAI |
| `search_youth_policies` | 나이·지역·상황 기반 청년정책 검색 | 온통청년 OpenAPI |
| `generate_resume_tip` | 자기소개서 첨삭과 예상 면접질문 | OpenAI |
| `build_career_action_plan` | 시간·비용·경험·불안 장벽을 반영한 7일 실행계획 | 외부 API 없음 |

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
MOCK_MODE=true
LIVE_API_ENABLED=false
```

- 사람인: 공식 `https://oapi.saramin.co.kr/job-search`
- 온통청년: 공식 공개 문서의 `https://www.youthcenter.go.kr/opi/youthPlcyList.do`
- OpenAI: 진로 분석과 자기소개서 코칭

키가 없거나 `MOCK_MODE=true`이면 데모 응답을 반환합니다. 키가 있더라도
`MOCK_MODE=false`와 `LIVE_API_ENABLED=true`를 모두 설정해야만 외부 API를 호출합니다. 데모 카드에는 `데모` 태그가
붙으며, 가짜 상세 주소 대신 사람인·온통청년 공식 검색 페이지로 연결됩니다. 마감일은 실행일
기준으로 생성해 오래된 데모가 실제 공고처럼 오인되지 않도록 했습니다.
Mock 데이터는 IT에 치우치지 않도록 복지·돌봄·디자인·사무·제조·물류와 비수도권 공고,
재학생·프리랜서·가족돌봄청년·마음건강 등 14개 정책 상황을 포함합니다. 정확한 결과가 0건이면
조건을 넓힌 참고 결과임을 명시해 막다른 화면을 피합니다.

자기소개서 원문은 OpenAI 연동 시 API로 전송됩니다. 서버가 영구 저장하지는 않지만 동일 입력
응답 캐시가 최대 1시간 유지될 수 있습니다. 캐시 키에는 원문 대신 SHA-256 해시만 저장합니다.
실제 주민번호, 계좌번호, 연락처 등 불필요한 개인정보는 입력하지 마세요.

### 공개 배포의 API 키 원칙

- GitHub, Dockerfile, 이미지, MCP 응답에는 키를 넣지 않습니다.
- 현재 PlayMCP in KC Git/컨테이너 등록 가이드에 Secret 주입 단계가 명시되어 있지 않으므로,
  해당 화면에서 바로 배포할 때는 기본 keyless 데모 모드를 유지합니다.
- 실시간 시연은 Secret 환경변수를 지원하는 서버에 별도로 배포한 뒤 HTTPS `/mcp` 주소를 등록합니다.
- 개인 기본 키 대신 출품 전용 프로젝트 키를 만들고 공급자 측 사용 알림·한도도 함께 설정합니다.
- 앱 내부 SQLite 한도는 인스턴스 단위 보호입니다. 여러 인스턴스를 쓰면 공급자 측 제한이나 공유 저장소가 추가로 필요합니다.

기본 보호값은 사람인 400회/일, 온통청년 300회/일, OpenAI 100회/일,
외부 API 동시 4회, OpenAI 동시 2회입니다. 모두 `.env.example`에서 낮출 수 있습니다.

## Docker / PlayMCP in KC

Git 소스 빌드 입력값:

- Git URL: `https://github.com/tearfulheart88/JobTalk`
- Branch/ref: `main`
- Dockerfile path: `Dockerfile`
- Endpoint path: `/mcp`

```powershell
docker build -t jobtalk .
docker run --rm -p 8001:8000 -e MOCK_MODE=true jobtalk
```

컨테이너는 non-root 사용자로 실행되고 `/health`를 점검합니다. 컨테이너 내부 기본 포트는
PlayMCP in KC 기본값과 같은 8000이며, 배포 플랫폼이 `PORT`를 주입하면 그 값을 사용합니다.
로컬에서 `python server.py`로 직접 실행할 때의 기본 포트는 8001입니다.

Secret 저장을 지원하는 별도 호스팅에서만 `MOCK_MODE=false`, `LIVE_API_ENABLED=true`와
필요한 키를 서버 환경변수로 설정하세요. 키를 `docker build --build-arg`로 전달하면 이미지
레이어에 남을 수 있으므로 사용하지 않습니다.

세부 Tool 스키마와 환경변수는 [careertalk/README.md](careertalk/README.md)를 참고하세요.
