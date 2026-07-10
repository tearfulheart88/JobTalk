"""
Tool 1: search_jobs
===================
사람인 OpenAPI 로 맞춤 채용공고를 검색한다.

입력: keywords, loc_cd, job_mid_cd, edu_lv, count, start
출력: 공고 리스트 (회사명, 직무, 지역, 마감일, 연봉, URL)

API: GET https://oapi.saramin.co.kr/job-search
인증: access-key 쿼리 파라미터
제약: 1일 500회, 페이지당 최대 110건

API 키가 없거나 MOCK_MODE=true 면 샘플 데이터를 반환한다.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import urllib.parse
from typing import Any

import httpx

from .common import (
    cache_get,
    cache_set,
    env_ttl,
    get_saramin_key,
    is_mock_mode,
    make_cache_key,
    rate_limit_exceeded,
    response_cache_enabled,
)
from .formatters import job_cards

logger = logging.getLogger("careertalk.search_jobs")
_KST = _dt.timezone(_dt.timedelta(hours=9), name="KST")

SARAMIN_ENDPOINT = "https://oapi.saramin.co.kr/job-search"


# ──────────────────────────────────────────────
# Mock 데이터 (API 키가 없을 때 사용)
# ──────────────────────────────────────────────
_MOCK_JOBS: list[dict[str, Any]] = [
    {
        "company_name": "(주)테크스타트",
        "title": "백엔드 개발자 (Node.js/Python) 신입~3년",
        "location": "서울 > 강남구",
        "job_type": "정규직",
        "industry": "IT 서비스",
        "experience": "신입~3년",
        "education": "대학교졸업(4년)이상",
        "salary": "3,000~4,000만원",
        "deadline": "2026-07-15",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-1",
        "keyword": "Node.js,Python,AWS",
    },
    {
        "company_name": "(주)데이터랩스",
        "title": "프론트엔드 개발자 (React/TypeScript)",
        "location": "서울 > 성동구",
        "job_type": "정규직",
        "industry": "데이터/AI",
        "experience": "경력 1~5년",
        "education": "대학교졸업(4년)이상",
        "salary": "4,000~5,500만원",
        "deadline": "2026-07-20",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-2",
        "keyword": "React,TypeScript,Next.js",
    },
    {
        "company_name": "(주)클라우드소프트",
        "title": "데브옵스 엔지니어 (Kubernetes/AWS)",
        "location": "경기 > 성남시 분당구",
        "job_type": "정규직",
        "industry": "클라우드 인프라",
        "experience": "경력 3~7년",
        "education": "대학교졸업(4년)이상",
        "salary": "5,000~7,000만원",
        "deadline": "2026-07-25",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-3",
        "keyword": "Kubernetes,AWS,Terraform",
    },
    {
        "company_name": "(주)AI리서치",
        "title": "머신러닝 엔지니어 신입 (NLP/LLM)",
        "location": "서울 > 마포구",
        "job_type": "계약직→정규직",
        "industry": "AI/ML",
        "experience": "신입",
        "education": "대학원졸업(석사)이상",
        "salary": "4,500~6,000만원",
        "deadline": "2026-07-18",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-4",
        "keyword": "Python,PyTorch,NLP,LLM",
    },
    {
        "company_name": "(주)모바일크래프트",
        "title": "iOS 개발자 (Swift/SwiftUI)",
        "location": "서울 > 영등포구",
        "job_type": "정규직",
        "industry": "모바일",
        "experience": "경력 2~6년",
        "education": "대학교졸업(4년)이상",
        "salary": "4,500~6,500만원",
        "deadline": "2026-07-22",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-5",
        "keyword": "Swift,SwiftUI,iOS",
    },
]


def _mock_search(keywords: str, count: int) -> dict[str, Any]:
    """Mock 모드 — 키워드가 비어있으면 전체, 있으면 토큰 단위 매칭(매칭 수 내림차순)."""
    today = _dt.datetime.now(_KST).date()
    demo_jobs: list[dict[str, Any]] = []
    for index, source in enumerate(_MOCK_JOBS):
        job = dict(source)
        searchword = keywords or str(job.get("title", "채용"))
        job["deadline"] = (today + _dt.timedelta(days=7 + index * 4)).isoformat()
        job["url"] = (
            "https://www.saramin.co.kr/zf_user/search?searchword="
            + urllib.parse.quote_plus(searchword)
        )
        job["is_demo"] = True
        demo_jobs.append(job)

    if keywords:
        # "프론트엔드 React" 같은 다단어 검색도 동작하도록 토큰별로 매칭
        tokens = [t for t in keywords.lower().replace(",", " ").split() if t]
        scored: list[tuple[int, dict[str, Any]]] = []
        for j in demo_jobs:
            haystack = f"{j['title']} {j['keyword']} {j['company_name']}".lower()
            matches = sum(1 for t in tokens if t in haystack)
            if matches:
                scored.append((matches, j))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        filtered = [j for _, j in scored]
    else:
        filtered = demo_jobs

    jobs = filtered[:count]
    return {
        "total": len(jobs),
        "count": len(jobs),
        "start": 0,
        "source": "mock",
        "demo_data": True,
        "jobs": jobs,
        "kakao_cards": job_cards(jobs),
        "message": f"[Mock 모드] 채용공고 {len(jobs)}건 검색 (실제 API 키 설정 시 실제 데이터 반환)",
    }


def _bounded_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    """문자열/None 입력도 안전하게 정수 범위로 보정."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _field_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name", "")
    if value in (None, "None", "null"):
        return ""
    return str(value)


def _normalize_deadline(value: Any) -> str:
    """사람인 마감일 값을 Kakao 카드 D-day 계산용 ISO 날짜로 정규화."""
    if value in (None, "", "None"):
        return ""
    text = str(value).strip()

    if text.isdigit():
        if len(text) == 8:
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        try:
            timestamp = int(text)
            if timestamp > 10_000_000_000:
                timestamp = timestamp // 1000
            return _dt.datetime.fromtimestamp(timestamp).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return text

    try:
        return _dt.date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return text


def _parse_saramin_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    """사람인 JSON 응답을 표준 형태로 변환."""
    jobs_root = _as_dict(data.get("jobs", {}))
    raw_jobs = jobs_root.get("job", [])
    if isinstance(raw_jobs, dict):
        # 단건 응답도 list 로 감싸줌
        raw_jobs = [raw_jobs]

    parsed: list[dict[str, Any]] = []
    for j in raw_jobs:
        if not isinstance(j, dict):
            continue
        company = _as_dict(_as_dict(j.get("company", {})).get("detail", {}))
        position = _as_dict(j.get("position", {}))
        location = position.get("location", {})
        job_type = position.get("job-type", {})
        industry = position.get("industry", {})
        experience = position.get("experience-level", {})
        education = position.get("required-education-level", {})
        salary = j.get("salary", {})

        parsed.append({
            "company_name": _field_name(company),
            "title": _field_name(position.get("title", "")),
            "location": _field_name(location),
            "job_type": _field_name(job_type),
            "industry": _field_name(industry),
            "experience": _field_name(experience),
            "education": _field_name(education),
            "salary": _field_name(salary),
            "deadline": _normalize_deadline(j.get("expiration-date", "")),
            "url": _field_name(j.get("url", "")),
            "keyword": _field_name(j.get("keyword", "")),
            "active": j.get("active"),
            "id": _field_name(j.get("id", "")),
        })
    return parsed


def _error_result(error: str, detail: str, *, start: int = 0) -> dict[str, Any]:
    return {
        "error": error,
        "detail": detail,
        "total": 0,
        "count": 0,
        "start": start,
        "source": "saramin",
        "jobs": [],
        "kakao_cards": [],
        "message": error,
    }


async def search_jobs(
    keywords: str = "",
    loc_cd: str = "",
    job_mid_cd: str = "",
    edu_lv: str = "",
    count: int = 10,
    start: int = 0,
) -> dict[str, Any]:
    """
    맞춤 채용공고를 검색합니다. (사람인 OpenAPI)

    Args:
        keywords: 검색 키워드 (예: "백엔드", "AI", "프론트엔드 React")
        loc_cd: 지역코드 (예: "101000" 서울). 사람인 코드표 참조.
        job_mid_cd: 직무 대분류 코드 (예: "22" IT개발·데이터)
        edu_lv: 학력 코드 (0~9, 예: 7=대학교졸업(4년))
        count: 페이지당 결과 수 (기본 10, 최대 110)
        start: 시작 오프셋 (0부터)

    Returns:
        공고 리스트 (회사명, 직무, 지역, 마감일, 연봉, URL) + 검색 메타정보
    """
    keywords = str(keywords or "").strip()
    loc_cd = str(loc_cd or "").strip()
    job_mid_cd = str(job_mid_cd or "").strip()
    edu_lv = str(edu_lv or "").strip()
    count = _bounded_int(count, 10, 1, 110)
    start = _bounded_int(start, 0, 0, 1_000_000)
    if len(keywords) > 200:
        return _error_result("keywords는 200자 이하여야 합니다.", "input_validation", start=start)
    if any(len(value) > 40 for value in (loc_cd, job_mid_cd, edu_lv)):
        return _error_result("검색 코드는 항목별 40자 이하여야 합니다.", "input_validation", start=start)

    # ── 응답 캐시 조회 (사람인 일일 500회 한도 보호) ──
    cache_on = response_cache_enabled()
    cache_key = make_cache_key(
        "search_jobs", keywords=keywords, loc_cd=loc_cd,
        job_mid_cd=job_mid_cd, edu_lv=edu_lv, count=count, start=start,
    )
    if cache_on:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    # ── Mock 모드 ──
    if is_mock_mode() or not get_saramin_key():
        return _mock_search(keywords, count)

    # ── 레이트리밋 (사람인 일일 500회 한도 보호 — 캐시 히트는 위에서 반환됨) ──
    limited = rate_limit_exceeded("external")
    if limited:
        return _error_result(limited, "rate_limited", start=start)

    # ── 실제 API 호출 ──
    params: dict[str, Any] = {
        "access-key": get_saramin_key(),
        "keywords": keywords,
        "count": count,
        "start": start,
        "sort": "pd",  # 최신 게시일 역순
    }
    if loc_cd:
        params["loc_cd"] = loc_cd
    if job_mid_cd:
        params["job_mid_cd"] = job_mid_cd
    if edu_lv:
        params["edu_lv"] = edu_lv

    headers = {"Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                SARAMIN_ENDPOINT, params=params, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("사람인 API HTTP 오류: %s (keywords=%r)", e.response.status_code, keywords)
        return _error_result(f"사람인 API HTTP 오류: {e.response.status_code}", str(e), start=start)
    except (httpx.RequestError, json.JSONDecodeError) as e:
        logger.warning("사람인 API 요청 실패: %s: %s (keywords=%r)", type(e).__name__, e, keywords)
        return _error_result(f"사람인 API 요청 실패: {type(e).__name__}", str(e), start=start)

    jobs = _parse_saramin_response(data)
    jobs_meta = _as_dict(data.get("jobs", {}))

    result = {
        "total": _safe_int(jobs_meta.get("total", len(jobs)), len(jobs)),
        "count": len(jobs),
        "start": _safe_int(jobs_meta.get("start", start), start),
        "source": "saramin",
        "jobs": jobs,
        "kakao_cards": job_cards(jobs),
        "message": f"채용공고 {len(jobs)}건 검색 완료 (전체 {jobs_meta.get('total', '?')}건)",
    }
    if cache_on:
        cache_set(cache_key, result, env_ttl("JOBS_CACHE_TTL", 600))
    return result
