"""
CareerTalk MCP Server
=====================
청년 진로·취업 AI 멘토 — MCP(Model Context Protocol) 서버

4개 Tool 제공:
  1. search_jobs           — 맞춤 채용공고 검색 (사람인 OpenAPI)
  2. analyze_job_fit       — AI 진로 적성 진단 및 직무 추천 (LLM)
  3. search_youth_policies — 청년정책·지원금 매칭 (온통청년 OpenAPI)
  4. generate_resume_tip   — 자기소개서 첨삭 + 면접 예상질문 (LLM)

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

from tools.search_jobs import search_jobs as _search_jobs  # noqa: E402
from tools.analyze_job_fit import analyze_job_fit as _analyze_job_fit  # noqa: E402
from tools.search_youth_policies import search_youth_policies as _search_youth_policies  # noqa: E402
from tools.generate_resume_tip import generate_resume_tip as _generate_resume_tip  # noqa: E402
from tools.common import (  # noqa: E402
    is_mock_mode,
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
    configured = [bool(get_saramin_key()), bool(get_youth_key()), bool(llm_available())]
    if all(configured):
        return "live"
    if any(configured):
        return "mixed"
    return "mock"


# ──────────────────────────────────────────────
# MCP 서버 인스턴스
# ──────────────────────────────────────────────
mcp = FastMCP(
    "CareerTalk",
    instructions=(
        "CareerTalk은 청년 진로·취업을 돕는 AI 멘토 MCP 서버입니다. "
        "4개 도구를 제공합니다:\n"
        "1. search_jobs — 맞춤 채용공고 검색 (사람인 OpenAPI)\n"
        "2. analyze_job_fit — AI 진로 적성 진단 및 직무 추천\n"
        "3. search_youth_policies — 청년정책·지원금 매칭 (온통청년)\n"
        "4. generate_resume_tip — 자기소개서 첨삭 + 면접 예상질문 생성\n\n"
        "모든 응답은 한국어로 제공됩니다."
    ),
)


# ──────────────────────────────────────────────
# Tool 등록 — tools/ 모듈의 함수를 직접 등록한다.
# 시그니처·docstring(파라미터 설명 포함)은 각 모듈이 단일 소스.
# ──────────────────────────────────────────────
mcp.tool()(_search_jobs)             # Tool 1: 맞춤 채용공고 검색 (사람인 OpenAPI)
mcp.tool()(_analyze_job_fit)         # Tool 2: AI 진로 적성 진단 및 직무 추천 (LLM)
mcp.tool()(_search_youth_policies)   # Tool 3: 청년정책·지원금 매칭 (온통청년 OpenAPI)
mcp.tool()(_generate_resume_tip)     # Tool 4: 자소서 첨삭 + 면접 예상질문 (LLM)


# ──────────────────────────────────────────────
# Resource: 서버 상태 조회 (디버그/모니터링용)
# ──────────────────────────────────────────────
@mcp.resource("careertalk://status")
def server_status() -> str:
    """CareerTalk 서버의 현재 설정 상태를 반환합니다."""
    import json

    status = {
        "server": "CareerTalk MCP",
        "tools": ["search_jobs", "analyze_job_fit", "search_youth_policies", "generate_resume_tip"],
        "mode": _runtime_mode(),
        "api_keys": {
            "saramin": "configured" if get_saramin_key() else "missing (using mock)",
            "youth_center": "configured" if get_youth_key() else "missing (using mock)",
            "llm": "configured" if llm_available() else "missing (using mock)",
        },
        "features": [
            "prompt_caching (OpenAI 자동 프리픽스 캐싱)",
            "response_cache (동일 입력 TTL 캐시 — 사람인 일일한도·LLM 비용 절감)",
            "kakao_cards (카드형 위젯 렌더링 — 진로/공고/정책/코칭)",
            "youth_api_v2 (온통청년 현행 getPlcy + 구버전 동시 지원)",
            "async_llm (AsyncOpenAI + 타임아웃 — 이벤트 루프 비블로킹)",
            "rate_limit (외부 API·LLM 분당 호출 제한 — 비용·한도 보호)",
        ],
        "rate_limit": "enabled" if rate_limit_enabled() else "disabled",
        "transport": os.environ.get("MCP_TRANSPORT", "streamable-http"),
    }
    return json.dumps(status, ensure_ascii=False, indent=2)


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
    parser.add_argument("--mock", action="store_true", help="외부 API 키 없이 샘플 데이터로 실행")
    return parser.parse_args()


def _apply_cli_args(args: argparse.Namespace) -> tuple[str, str, int]:
    if args.mock:
        os.environ["MOCK_MODE"] = "true"
    if args.transport:
        os.environ["MCP_TRANSPORT"] = args.transport
    if args.host:
        os.environ["MCP_HOST"] = args.host
    if args.port is not None:
        os.environ["MCP_PORT"] = str(args.port)

    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("MCP_PORT", "8001"))
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
    print(f"  Tools:      search_jobs, analyze_job_fit, search_youth_policies, generate_resume_tip")
    print()
    print("  API key status:")
    print(f"    saramin:      {'configured' if get_saramin_key() else 'missing (Mock)'}")
    print(f"    youth_center: {'configured' if get_youth_key() else 'missing (Mock)'}")
    print(f"    llm:          {'configured' if llm_available() else 'missing (Mock)'}")
    print(f"  Rate limit:   {'enabled' if rate_limit_enabled() else 'disabled (mock mode)'}")
    print()

    if transport == "streamable-http":
        try:
            mcp.run(transport=transport, host=host, port=port)
        except TypeError:
            # 현재 MCP SDK 일부 버전은 run() 에 host/port 인자를 받지 않는다.
            # streamable-http 는 Starlette 앱을 직접 uvicorn 으로 서빙해 포트를 고정한다.
            import uvicorn

            app = mcp.streamable_http_app()
            uvicorn.run(app, host=host, port=port)
    else:
        mcp.run(transport=transport)
