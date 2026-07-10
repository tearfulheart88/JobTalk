"""
공통 유틸리티 — 환경변수 로드, Mock 모드 판별, LLM 클라이언트 팩토리.
모든 도구 모듈이 공유한다.
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any

logger = logging.getLogger("careertalk")

try:
    from dotenv import load_dotenv

    _PROJECT_DIR = Path(__file__).resolve().parents[1]

    def _candidate_env_dirs() -> list[Path]:
        # 프로젝트 루트(careertalk_진로톡/)·실행 위치·서버 폴더(careertalk/)만 탐색.
        # 상위 폴더를 넓게 뒤지면 무관한 프로젝트의 .env 가 섞여 들어올 수 있다.
        dirs: list[Path] = []
        for base in (_PROJECT_DIR.parent, Path.cwd(), _PROJECT_DIR):
            if base not in dirs:
                dirs.append(base)
        return dirs

    def _load_env_files() -> None:
        existing_env = dict(os.environ)
        for env_dir in _candidate_env_dirs():
            for env_name in (".env", ".env.local"):
                env_path = env_dir / env_name
                if env_path.exists():
                    load_dotenv(env_path, override=True)
        # 실제 프로세스 환경변수는 파일보다 우선한다.
        for key, value in existing_env.items():
            os.environ[key] = value

    _load_env_files()
except ImportError:
    # dotenv 가 없어도 환경변수로 동작 가능
    pass


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def is_mock_mode() -> bool:
    """MOCK_MODE=true 이면 외부 API 호출 없이 Mock 데이터를 반환한다."""
    return (os.getenv("MOCK_MODE", "false") or "").strip().lower() in ("true", "1", "yes")


def get_saramin_key() -> str | None:
    return _env_value("SARAMIN_ACCESS_KEY")


def get_youth_key() -> str | None:
    return _env_value("YOUTH_OPEN_API_KEY")


def get_openai_key() -> str | None:
    return _env_value("OPENAI_API_KEY")


def get_llm_provider() -> str | None:
    """사용 가능한 LLM provider 이름 반환. OpenAI만 지원. 없으면 None."""
    if get_openai_key():
        return "openai"
    return None


def llm_available() -> bool:
    return get_llm_provider() is not None


def _llm_timeout() -> float:
    """LLM 호출 타임아웃(초). 기본 30초 — 서버가 매달리는 것을 방지."""
    try:
        return max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "30")))
    except (TypeError, ValueError):
        return 30.0


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 1200,
    json_mode: bool = False,
) -> str:
    """
    비동기 LLM 호출. OpenAI 를 사용하고, 없거나 실패하면 빈 문자열을 반환한다.
    호출측은 빈 문자열을 받으면 Mock fallback 으로 응답한다.

    - **AsyncOpenAI + 타임아웃(기본 30초)**: 동기 호출로 이벤트 루프가 얼거나
      응답 지연에 서버가 매달리는 것을 방지. 실패 원인은 warning 로그로 남긴다.

    지연·비용 최적화 (기획서 §2.3):
      - **Prompt Caching**: OpenAI 는 1024토큰 이상 동일 접두사를 자동 캐싱하므로
        시스템 프롬프트를 맨 앞에 고정하는 것만으로 입력비용·TTFT 절감.
      - 경량 모델 기본값(gpt-4o-mini)으로 비용·지연 최소화.
    """
    provider = get_llm_provider()
    if provider == "openai":
        model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=get_openai_key(),
                timeout=_llm_timeout(),
                max_retries=1,
            )
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                # OpenAI 는 1024토큰 이상 동일 접두사를 자동 캐싱(시스템 프롬프트를 맨 앞에 고정).
                resp = await client.chat.completions.create(**kwargs)
            except Exception as first_error:
                if not json_mode:
                    raise
                # 일부 모델은 response_format 미지원 — JSON 모드 없이 1회 재시도.
                logger.warning(
                    "LLM JSON 모드 호출 실패(%s: %s) — response_format 없이 재시도",
                    type(first_error).__name__, first_error,
                )
                kwargs.pop("response_format", None)
                resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(
                "LLM 호출 실패 — Mock 폴백 (model=%s, %s: %s)",
                model_name, type(e).__name__, e,
            )
            return ""

    return ""


def parse_json_object(text: str) -> dict[str, Any] | None:
    """LLM 응답에서 JSON object 하나를 최대한 안전하게 추출한다."""
    if not text:
        return None

    candidates: list[str] = []
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end > start:
            candidates.append(text[start:end].strip())
    if "```" in text:
        start = text.find("```") + len("```")
        end = text.find("```", start)
        if end > start:
            candidates.append(text[start:end].strip())
    candidates.append(text.strip())

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        for idx, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


# ──────────────────────────────────────────────
# 응답 캐시 (기획서 §2.3 "Response Cache")
# ──────────────────────────────────────────────
# 동일 입력 재요청 시 외부 API / LLM 재호출 없이 즉시 반환한다.
#   - 사람인 OpenAPI 일일 500회 한도 보호
#   - LLM 비용·지연 절감
# 프로세스 메모리 기반 TTL 캐시 (단일 인스턴스 MVP 범위).
_RESPONSE_CACHE: dict[str, tuple[float, Any]] = {}


def response_cache_enabled() -> bool:
    """Mock 모드에서는 데모 일관성을 위해 캐시를 끈다."""
    if is_mock_mode():
        return False
    return (os.getenv("RESPONSE_CACHE_ENABLED", "true") or "").strip().lower() in ("true", "1", "yes")


def make_cache_key(name: str, **params: Any) -> str:
    """민감한 원문을 메모리 키에 남기지 않는 안정적 SHA-256 캐시 키."""
    payload = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{name}:{digest}"


def _cache_max_entries() -> int:
    try:
        return max(1, int(os.getenv("RESPONSE_CACHE_MAX_ENTRIES", "256")))
    except (TypeError, ValueError):
        return 256


def _purge_expired_cache(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    expired = [key for key, (expires_at, _) in _RESPONSE_CACHE.items() if now >= expires_at]
    for key in expired:
        _RESPONSE_CACHE.pop(key, None)


def cache_get(key: str) -> Any | None:
    """TTL 이 유효하면 캐시값, 만료/없음이면 None."""
    hit = _RESPONSE_CACHE.get(key)
    if hit is None:
        return None
    expires_at, value = hit
    if time.monotonic() >= expires_at:
        _RESPONSE_CACHE.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any, ttl: float) -> None:
    if ttl <= 0:
        _RESPONSE_CACHE.pop(key, None)
        return
    _purge_expired_cache()
    max_entries = _cache_max_entries()
    while len(_RESPONSE_CACHE) >= max_entries:
        oldest_key = min(_RESPONSE_CACHE, key=lambda k: _RESPONSE_CACHE[k][0])
        _RESPONSE_CACHE.pop(oldest_key, None)
    _RESPONSE_CACHE[key] = (time.monotonic() + ttl, value)


def cache_clear() -> None:
    """테스트/운영용 캐시 비우기."""
    _RESPONSE_CACHE.clear()


def env_ttl(var: str, default: float) -> float:
    """환경변수에서 TTL(초)을 읽되 실패 시 기본값."""
    try:
        return max(0.0, float(os.getenv(var, "") or default))
    except (TypeError, ValueError):
        return default


def _truncate(text: str, limit: int = 120) -> str:
    """로그/디버그용 문자열 축약."""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


# ──────────────────────────────────────────────
# 레이트리미터 (공개 배포 방어)
# ──────────────────────────────────────────────
# 프로세스 전역 슬라이딩 윈도우(60초). MCP 도구 호출 시점에는 클라이언트 IP 를
# 알 수 없으므로 "전체 호출량" 기준으로 외부 API 한도·LLM 비용을 보호한다.
#   - scope "llm":      LLM_RATE_LIMIT_PER_MINUTE  (기본 10회/분)
#   - scope "external": RATE_LIMIT_PER_MINUTE      (기본 30회/분)
# Mock 모드에서는 비활성 (데모·테스트 일관성). RATE_LIMIT_ENABLED=false 로 전체 해제.
_RATE_WINDOWS: dict[str, deque[float]] = {}

_RATE_DEFAULTS = {"llm": 10, "external": 30}


def rate_limit_enabled() -> bool:
    if is_mock_mode():
        return False
    return (os.getenv("RATE_LIMIT_ENABLED", "true") or "").strip().lower() in ("true", "1", "yes")


def _rate_limit_per_minute(scope: str) -> int:
    var = "LLM_RATE_LIMIT_PER_MINUTE" if scope == "llm" else "RATE_LIMIT_PER_MINUTE"
    default = _RATE_DEFAULTS.get(scope, 30)
    try:
        return max(1, int(os.getenv(var, "") or default))
    except (TypeError, ValueError):
        return default


def rate_limit_exceeded(scope: str) -> str | None:
    """
    한도 초과 시 사용자 안내 메시지, 여유가 있으면 None 을 반환하고 호출 1회를 기록.
    캐시 히트·Mock 응답은 비용이 없으므로 이 함수를 타지 않는다 —
    실제 외부 API / LLM 호출 직전에만 검사할 것.
    """
    if not rate_limit_enabled():
        return None
    now = time.monotonic()
    window = _RATE_WINDOWS.setdefault(scope, deque())
    while window and now - window[0] >= 60.0:
        window.popleft()
    limit = _rate_limit_per_minute(scope)
    if len(window) >= limit:
        logger.warning("레이트리밋 초과 (scope=%s, limit=%d/분)", scope, limit)
        return f"요청이 몰려 잠시 제한 중입니다. 약 1분 후 다시 시도해주세요. (분당 {limit}회 제한)"
    window.append(now)
    return None


def rate_limit_reset() -> None:
    """테스트용 레이트리미터 초기화."""
    _RATE_WINDOWS.clear()
