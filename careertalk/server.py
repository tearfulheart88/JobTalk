"""
CareerTalk MCP Server
=====================
청년 진로·취업 AI 멘토 — MCP(Model Context Protocol) 서버

6개 Tool 제공:
  1. career_guide          — 첫 사용 안내·예시·FAQ·개인정보 원칙
  2. search_jobs           — 맞춤 채용공고 검색 (사람인 OpenAPI)
  3. analyze_job_fit       — AI 진로 적성 진단 및 직무 추천 (LLM)
  4. search_youth_policies — 청년정책·지원금 매칭 (온통청년 OpenAPI)
  5. generate_resume_tip   — 자기소개서 첨삭 + 면접 예상질문 (LLM)
  6. build_career_action_plan — 취업 장벽을 반영한 7일 실행계획

PlayMCP(https://playmcp.kakao.com) 등록용 — streamable-http 전송.
로컬 테스트: python server.py → http://localhost:8001/mcp

API 키가 없어도 Mock 모드로 동작합니다 (.env 에 MOCK_MODE=true 또는 키 미설정).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ──────────────────────────────────────────────
# 경로 설정 — tools/ 모듈 임포트를 위해 자신의 디렉토리를 path 맨에 추가
# ──────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from tools.search_jobs import search_jobs as _search_jobs  # noqa: E402
from tools.analyze_job_fit import analyze_job_fit as _analyze_job_fit  # noqa: E402
from tools.search_youth_policies import search_youth_policies as _search_youth_policies  # noqa: E402
from tools.generate_resume_tip import generate_resume_tip as _generate_resume_tip  # noqa: E402
from tools.build_career_action_plan import build_career_action_plan as _build_career_action_plan  # noqa: E402
from tools.career_guide import career_guide as _career_guide  # noqa: E402
from tools.common import (  # noqa: E402
    is_mock_mode,
    live_api_enabled,
    get_saramin_key,
    get_youth_key,
    llm_available,
    rate_limit_enabled,
)

# 라이브 장애 진단용 로깅 — LLM 폴백·외부 API 오류·레이트리밋이 warning 으로 남는다.
logging.basicConfig(
    level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def _runtime_mode() -> str:
    if is_mock_mode():
        return "mock"
    if not live_api_enabled():
        return "safe_fallback"
    configured = [bool(get_saramin_key()), bool(get_youth_key()), bool(llm_available())]
    if all(configured):
        return "live"
    if any(configured):
        return "mixed"
    return "mock"


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _transport_security() -> TransportSecuritySettings:
    endpoint_host = os.environ.get(
        "PLAYMCP_ENDPOINT_HOST",
        "jobtalk-mcp.playmcp-endpoint.kakaocloud.io",
    ).strip()
    allowed_hosts = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
        "jobtalk-mcp",
        "jobtalk-mcp:*",
    ]
    allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
        "https://playmcp.kakaocloud.io",
        "https://playmcp.kakao.com",
    ]
    if endpoint_host:
        allowed_hosts.extend([endpoint_host, f"{endpoint_host}:*"])
        allowed_origins.extend(
            [f"https://{endpoint_host}", f"https://{endpoint_host}:*"]
        )
    allowed_hosts.extend(_csv_env("MCP_ALLOWED_HOSTS"))
    allowed_origins.extend(_csv_env("MCP_ALLOWED_ORIGINS"))
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(dict.fromkeys(allowed_origins)),
    )


# ──────────────────────────────────────────────
# MCP 서버 인스턴스
# ──────────────────────────────────────────────
mcp = FastMCP(
    "CareerTalk",
    instructions=(
        "CareerTalk은 청년 진로·취업을 돕는 AI 멘토 MCP 서버입니다. "
        "6개 도구를 제공합니다:\n"
        "1. career_guide — 첫 사용 안내·사용 예시·FAQ·개인정보 원칙\n"
        "2. search_jobs — 맞춤 채용공고 검색 (사람인 OpenAPI)\n"
        "3. analyze_job_fit — AI 진로 적성 진단 및 직무 추천\n"
        "4. search_youth_policies — 청년정책·지원금 매칭 (온통청년)\n"
        "5. generate_resume_tip — 자기소개서 첨삭 + 면접 예상질문 생성\n"
        "6. build_career_action_plan — 시간·비용·경험·불안 장벽을 반영한 7일 실행계획\n\n"
        "처음 방문했거나 사용법·도움말·FAQ를 물으면 career_guide를 먼저 호출하세요. "
        "사용자가 막막함이나 실행 방법을 물으면 build_career_action_plan을 우선 고려하고, "
        "실제 공고·정책·첨삭이 필요할 때 나머지 도구로 이어가세요. 모든 응답은 한국어로 제공합니다."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=_transport_security(),
)


# ──────────────────────────────────────────────
# Tool 등록 - PlayMCP 필수 annotations 5개와 영문 설명을 명시한다.
# ──────────────────────────────────────────────
def _read_only_annotations(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )

mcp.tool(
    title="Start CareerTalk | 진로톡 시작 안내",
    description=(
        "사용자가 처음 방문했거나 목적·사용법·예시·FAQ·개인정보 처리를 물을 때 먼저 호출합니다. "
        "Explains how to start and safely use CareerTalk(진로톡) with one-tap examples and built-in FAQs."
    ),
    annotations=_read_only_annotations("Start CareerTalk | 진로톡 시작 안내"),
)(_career_guide)

mcp.tool(
    title="Search Jobs | 채용공고 검색",
    description=(
        "사용자가 채용공고·일자리·신입 포지션을 찾을 때 호출합니다. Searches live or clearly "
        "labeled demo job listings for CareerTalk(진로톡) using keyword, region, role, and education filters."
    ),
    annotations=_read_only_annotations("Search Jobs | 채용공고 검색"),
)(_search_jobs)
mcp.tool(
    title="Analyze Career Fit | 직무 적합도 분석",
    description=(
        "사용자가 자신에게 맞는 직무나 진입 경로를 물을 때 호출합니다. Analyzes a user profile and "
        "recommends five career paths for CareerTalk(진로톡) using a protected LLM or deterministic fallback."
    ),
    annotations=_read_only_annotations("Analyze Career Fit | 직무 적합도 분석"),
)(_analyze_job_fit)
mcp.tool(
    title="Search Youth Policies | 청년정책 검색",
    description=(
        "사용자가 받을 수 있는 취업·교육·주거 지원을 물을 때 호출합니다. Searches live or clearly "
        "labeled demo youth policies for CareerTalk(진로톡) by age, region, and employment situation."
    ),
    annotations=_read_only_annotations("Search Youth Policies | 청년정책 검색"),
)(_search_youth_policies)
mcp.tool(
    title="Generate Resume Tips | 자소서 첨삭",
    description=(
        "사용자가 자기소개서 첨삭이나 면접 준비를 요청할 때 호출합니다. Generates resume revisions and "
        "interview preparation for CareerTalk(진로톡) using a protected LLM or deterministic fallback."
    ),
    annotations=_read_only_annotations("Generate Resume Tips | 자소서 첨삭"),
)(_generate_resume_tip)
mcp.tool(
    title="Build a 7-Day Career Plan | 7일 커리어 실행계획",
    description=(
        "사용자가 취업이 막막하거나 시간·비용·경험 부족 때문에 시작하지 못할 때 우선 호출합니다. "
        "Builds a private, barrier-aware seven-day micro-action plan for CareerTalk(진로톡) without an external API."
    ),
    annotations=_read_only_annotations("Build a 7-Day Career Plan | 7일 커리어 실행계획"),
)(_build_career_action_plan)


# ──────────────────────────────────────────────
# Resource: 서버 상태 조회 (디버그/모니터링용)
# ──────────────────────────────────────────────
@mcp.resource("careertalk://status")
def server_status() -> str:
    """CareerTalk 서버의 현재 설정 상태를 반환합니다."""
    import json

    status = {
        "server": "CareerTalk MCP",
        "tools": ["career_guide", "search_jobs", "analyze_job_fit", "search_youth_policies", "generate_resume_tip", "build_career_action_plan"],
        "mode": _runtime_mode(),
        "live_api_enabled": live_api_enabled(),
        "api_keys": {
            "saramin": "configured" if get_saramin_key() else "missing (using mock)",
            "youth_center": "configured" if get_youth_key() else "missing (using mock)",
            "llm": "configured" if llm_available() else "missing (using mock)",
        },
        "features": [
            "prompt_caching (OpenAI 자동 프리픽스 캐싱)",
            "response_cache (동일 입력 TTL 캐시 — 사람인 일일한도·LLM 비용 절감)",
            "kakao_cards (카드형 위젯 렌더링 — 진로/공고/정책/코칭)",
            "youth_api (온통청년 공식 youthPlcyList + 대체 응답 형식 파싱)",
            "async_llm (AsyncOpenAI + 타임아웃 — 이벤트 루프 비블로킹)",
            "rate_limit (외부 API·LLM 분당 호출 제한 — 비용·한도 보호)",
            "daily_quota (SQLite 기반 일일 호출 하드 가드)",
            "secret_redaction (오류·로그의 키 및 인증 URL 제거)",
        ],
        "rate_limit": "enabled" if rate_limit_enabled() else "disabled",
        "transport": os.environ.get("MCP_TRANSPORT", "streamable-http"),
    }
    return json.dumps(status, ensure_ascii=False, indent=2)


@mcp.custom_route("/", methods=["GET"])
async def root_status(_request: Request) -> JSONResponse:
    """배포 상태와 API 키 설정 여부만 노출하는 안전한 헬스 엔드포인트."""
    import json

    payload = json.loads(server_status())
    payload.update({"status": "ok", "version": "3.0.0", "endpoint": "/mcp"})
    return JSONResponse(payload)


@mcp.custom_route("/health", methods=["GET"])
async def health_status(request: Request) -> JSONResponse:
    return await root_status(request)


# ──────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="진로톡(CareerTalk) MCP 서버")
    parser.add_argument("--host", default=None, help="바인드 호스트 (기본: MCP_HOST 또는 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="바인드 포트 (기본: MCP_PORT 또는 8001)")
    parser.add_argument(
        "--transport",
        default=None,
        choices=["stdio", "sse", "streamable-http"],
        help="MCP 전송 방식 (기본: MCP_TRANSPORT 또는 streamable-http)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="외부 API 키 없이 샘플 데이터로 실행")
    mode.add_argument("--live", action="store_true", help="명시적으로 보호된 외부 API 호출 활성화")
    return parser.parse_args()


def _apply_cli_args(args: argparse.Namespace) -> tuple[str, str, int]:
    if args.mock:
        os.environ["MOCK_MODE"] = "true"
        os.environ["LIVE_API_ENABLED"] = "false"
    elif args.live:
        os.environ["MOCK_MODE"] = "false"
        os.environ["LIVE_API_ENABLED"] = "true"
    if args.transport:
        os.environ["MCP_TRANSPORT"] = args.transport
    if args.host:
        os.environ["MCP_HOST"] = args.host
    if args.port is not None:
        os.environ["MCP_PORT"] = str(args.port)

    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("MCP_PORT") or os.environ.get("PORT") or "8001")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        port = 8001
        os.environ["MCP_PORT"] = str(port)
    return transport, host, port


if __name__ == "__main__":
    transport, host, port = _apply_cli_args(_parse_args())

    mode_label = _runtime_mode().title()

    print("CareerTalk MCP Server starting...")
    print(f"  Transport: {transport}")
    print(f"  Endpoint:   http://{host}:{port}/mcp")
    print(f"  Mode:       {mode_label}")
    print("  Tools:      career_guide, search_jobs, analyze_job_fit, search_youth_policies, generate_resume_tip, build_career_action_plan")
    print()
    print("  API key status:")
    print(f"    saramin:      {'configured' if get_saramin_key() else 'missing (Mock)'}")
    print(f"    youth_center: {'configured' if get_youth_key() else 'missing (Mock)'}")
    print(f"    llm:          {'configured' if llm_available() else 'missing (Mock)'}")
    print(f"  Rate limit:   {'enabled' if rate_limit_enabled() else 'disabled (mock mode)'}")
    print()

    if transport == "streamable-http":
        import uvicorn

        uvicorn.run(mcp.streamable_http_app(), host=host, port=port)
    elif transport == "sse":
        import uvicorn

        uvicorn.run(mcp.sse_app(), host=host, port=port)
    else:
        mcp.run(transport=transport)
