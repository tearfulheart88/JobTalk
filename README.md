# JobTalk / 진로톡

청년 진로, 채용공고, 청년정책, 자기소개서 코칭을 제공하는 MCP 서버입니다.

## PlayMCP in KC

Git 소스 빌드로 등록할 때 입력값:

- Git URL: `https://github.com/tearfulheart88/JobTalk`
- Branch/ref: `main`
- Dockerfile 경로: `Dockerfile`

서버가 활성화되면 발급된 Endpoint URL을 PlayMCP 개발자 콘솔에 등록합니다. MCP 경로는 `/mcp`입니다.

## Local Test

```powershell
python tests\test_servers.py
```

## Local Run

```powershell
cd careertalk
python server.py --host 0.0.0.0 --port 8001 --transport streamable-http
```
