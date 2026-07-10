# 진로톡 개발 현황

최종 점검: 2026-07-10

## 현재 상태

- 공식 `FastMCP` 기반 stateless Streamable HTTP 서버
- endpoint `/mcp`, health endpoint `/health`
- Tool 4개 등록
- 통합·회귀 테스트 32개 통과
- 공식 MCP Python 클라이언트로 initialize, tools/list, tools/call 통과
- PlayMCP in KC용 Dockerfile 준비

## 이번 최종 점검 반영

1. 온통청년 기본 연동을 공식 공개 문서의 `youthPlcyList.do`/`openApiVlak`로 교정했습니다.
2. 대체 `getPlcy` 응답 파싱은 환경변수 선택 경로로 유지했습니다.
3. 클라우드 권장 구성인 stateless HTTP + JSON response를 적용했습니다.
4. `/health`와 안전한 API 키 설정 상태 조회를 추가했습니다.
5. Mock 채용·정책에 데모 표식을 붙이고 가짜 상세 URL을 공식 검색 페이지 링크로 교체했습니다.
6. Mock 마감일을 실행일 기준으로 생성해 데모가 오래되어도 모두 마감으로 보이지 않게 했습니다.
7. 자소서 원문이 캐시 키에 남지 않도록 SHA-256 키로 변경했습니다.
8. LLM 프롬프트에서 사용자 입력을 명령이 아닌 데이터로 명확히 구분했습니다.
9. 과도하게 긴 입력과 잘못된 나이를 차단했습니다.
10. 컨테이너를 non-root 사용자로 실행하고 healthcheck를 추가했습니다.

## 검증 명령

```powershell
python -m compileall -q .
python tests\test_servers.py
cd careertalk
python server.py --mock --host 127.0.0.1 --port 8001
```

## 외부 준비가 필요한 항목

- 실제 채용 검색: `SARAMIN_ACCESS_KEY`
- 실제 정책 검색: `YOUTH_OPEN_API_KEY`
- 실제 진로·자소서 LLM: `OPENAI_API_KEY`
- PlayMCP in KC 빌드 및 최종 등록
