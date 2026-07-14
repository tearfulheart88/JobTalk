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
    external_api_timeout,
    get_saramin_key,
    is_mock_mode,
    live_api_enabled,
    make_cache_key,
    rate_limit_exceeded,
    redact_secrets,
    release_call_slot,
    reserve_live_call,
    response_cache_enabled,
    safe_error_detail,
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
    {
        "company_name": "부산이음복지관",
        "title": "청년 사회복지사 신입 채용",
        "location": "부산 > 부산진구",
        "job_type": "정규직",
        "industry": "사회복지",
        "experience": "신입",
        "education": "전문대졸 이상",
        "salary": "2,800~3,300만원",
        "deadline": "2026-08-02",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-6",
        "keyword": "사회복지,복지사,상담,사람을 돕는 일,신입",
    },
    {
        "company_name": "대구늘봄케어",
        "title": "주간보호센터 돌봄 코디네이터",
        "location": "대구 > 수성구",
        "job_type": "계약직→정규직",
        "industry": "돌봄 서비스",
        "experience": "경력무관",
        "education": "고졸 이상",
        "salary": "월 240~280만원",
        "deadline": "2026-08-06",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-7",
        "keyword": "돌봄,요양,코디네이터,고졸,경력무관",
    },
    {
        "company_name": "(주)로컬웨이브",
        "title": "지역 브랜드 디지털 마케터 신입",
        "location": "대전 > 유성구",
        "job_type": "정규직",
        "industry": "광고/마케팅",
        "experience": "신입",
        "education": "학력무관",
        "salary": "2,900~3,500만원",
        "deadline": "2026-08-10",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-8",
        "keyword": "마케팅,SNS,콘텐츠,브랜드,신입,학력무관",
    },
    {
        "company_name": "(주)바른오피스",
        "title": "회계·경영지원 담당자 신입",
        "location": "인천 > 연수구",
        "job_type": "정규직",
        "industry": "기업 서비스",
        "experience": "신입",
        "education": "고졸 이상",
        "salary": "2,800~3,400만원",
        "deadline": "2026-08-14",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-9",
        "keyword": "회계,사무,경영지원,엑셀,고졸,신입",
    },
    {
        "company_name": "광주그린모빌리티",
        "title": "생산 품질관리 현장 인턴",
        "location": "광주 > 광산구",
        "job_type": "채용연계형 인턴",
        "industry": "제조/모빌리티",
        "experience": "경력무관",
        "education": "고졸 이상",
        "salary": "월 250만원",
        "deadline": "2026-08-18",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-10",
        "keyword": "생산,품질,제조,인턴,현장,고졸",
    },
    {
        "company_name": "(주)모두의제품",
        "title": "UX/UI 디자이너 주니어",
        "location": "서울 > 중구 (주 2회 원격)",
        "job_type": "정규직",
        "industry": "디지털 제품",
        "experience": "신입~2년",
        "education": "학력무관",
        "salary": "3,100~4,000만원",
        "deadline": "2026-08-22",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-11",
        "keyword": "UX,UI,Figma,디자인,포트폴리오,원격",
    },
    {
        "company_name": "부산데이터협동조합",
        "title": "공공데이터 분석가 신입",
        "location": "부산 > 해운대구",
        "job_type": "정규직",
        "industry": "데이터/공공",
        "experience": "신입",
        "education": "전문대졸 이상",
        "salary": "3,000~3,800만원",
        "deadline": "2026-08-26",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-12",
        "keyword": "데이터,Python,SQL,통계,공공데이터,신입",
    },
    {
        "company_name": "전북청년마음센터",
        "title": "청년 상담·프로그램 운영 매니저",
        "location": "전북 > 전주시",
        "job_type": "계약직",
        "industry": "청년지원/상담",
        "experience": "경력무관",
        "education": "대학교졸업(4년)이상",
        "salary": "월 260~300만원",
        "deadline": "2026-08-30",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-13",
        "keyword": "청년,상담,프로그램,복지,운영,사람을 돕는 일",
    },
    {
        "company_name": "울산스마트로지스",
        "title": "물류 운영·재고관리 신입",
        "location": "울산 > 남구",
        "job_type": "정규직",
        "industry": "물류/유통",
        "experience": "신입",
        "education": "고졸 이상",
        "salary": "3,000~3,600만원",
        "deadline": "2026-09-03",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-14",
        "keyword": "물류,유통,재고,운영,엑셀,신입,고졸",
    },
    {
        "company_name": "(주)페이지온",
        "title": "원격 콘텐츠 에디터·운영 인턴",
        "location": "전국 > 원격근무",
        "job_type": "채용연계형 인턴",
        "industry": "콘텐츠/교육",
        "experience": "경력무관",
        "education": "학력무관",
        "salary": "월 230만원",
        "deadline": "2026-09-07",
        "url": "https://www.saramin.co.kr/jobs/view?rec_idx=mock-15",
        "keyword": "글쓰기,콘텐츠,에디터,운영,인턴,원격,학력무관",
    },
]


def _text_filter(value: str) -> str:
    """Mock 데이터에서 의미 있게 비교할 수 있는 한글/영문 필터만 반환."""
    value = str(value or "").strip().lower()
    return value if any(ch.isalpha() for ch in value) else ""


def _mock_search(
    keywords: str,
    loc_cd: str,
    job_mid_cd: str,
    edu_lv: str,
    count: int,
) -> dict[str, Any]:
    """Mock 모드 — 다양한 직군을 토큰 점수로 검색하고 0건이면 조건 확장 결과를 제안."""
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

    location_filter = _text_filter(loc_cd)
    role_filter = _text_filter(job_mid_cd)
    education_filter = _text_filter(edu_lv)
    candidates = [
        job for job in demo_jobs
        if (not location_filter or location_filter in job["location"].lower())
        and (not role_filter or role_filter in f"{job['title']} {job['industry']} {job['keyword']}".lower())
        and (not education_filter or education_filter in job["education"].lower())
    ]

    if keywords:
        # "프론트엔드 React" 같은 다단어 검색도 동작하도록 토큰별로 매칭
        tokens = [t for t in keywords.lower().replace(",", " ").split() if t]
        scored: list[tuple[int, dict[str, Any]]] = []
        for j in candidates:
            haystack = (
                f"{j['title']} {j['keyword']} {j['company_name']} "
                f"{j['location']} {j['industry']} {j['experience']} {j['education']}"
            ).lower()
            matches = sum(1 for t in tokens if t in haystack)
            if matches:
                scored.append((matches, j))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        filtered = [j for _, j in scored]
    else:
        filtered = candidates

    exact_match_count = len(filtered)
    relaxed_filters: list[str] = []
    if not filtered:
        # 심사 데모에서 막다른 화면 대신, 조건을 넓힌 참고 결과를 정직하게 표시한다.
        location_only = [
            job for job in demo_jobs
            if not location_filter or location_filter in job["location"].lower()
        ]
        filtered = (location_only or demo_jobs)[: max(3, count)]
        relaxed_filters.append("키워드·직무·학력 조건")
        if location_filter and not location_only:
            relaxed_filters.append("지역 조건")
        for job in filtered:
            job["match_note"] = "정확히 일치하는 데모 공고가 없어 조건을 넓힌 참고 결과입니다."

    jobs = filtered[:count]
    return {
        "total": len(jobs),
        "count": len(jobs),
        "start": 0,
        "source": "mock",
        "demo_data": True,
        "exact_match_count": exact_match_count,
        "relaxed_filters": relaxed_filters,
        "filters": {
            "keywords": keywords,
            "location": loc_cd,
            "role": job_mid_cd,
            "education": edu_lv,
        },
        "jobs": jobs,
        "kakao_cards": job_cards(jobs),
        "quick_replies": ["신입 공고만", "지역 조건 넓혀줘", "맞는 직무 찾아줘", "7일 계획 만들기"],
        "message": (
            f"[Mock 모드] 정확히 맞는 데모 공고 {exact_match_count}건"
            if exact_match_count
            else f"[Mock 모드] 정확한 결과가 없어 조건을 넓힌 참고 공고 {len(jobs)}건"
        ) + " (API 연결 시 실시간 데이터 반환)",
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
    count = _bounded_int(count, 10, 1, 10)
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
    if is_mock_mode() or not live_api_enabled() or not get_saramin_key():
        return _mock_search(keywords, loc_cd, job_mid_cd, edu_lv, count)

    # ── 레이트리밋 (사람인 일일 500회 한도 보호 — 캐시 히트는 위에서 반환됨) ──
    limited = rate_limit_exceeded("external")
    if limited:
        return _error_result(limited, "rate_limited", start=start)

    denied = reserve_live_call("saramin")
    if denied:
        return _error_result(denied, "usage_guard", start=start)

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
        async with httpx.AsyncClient(timeout=external_api_timeout()) as client:
            resp = await client.get(
                SARAMIN_ENDPOINT, params=params, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("사람인 API HTTP 오류: %s (keywords=%r)", e.response.status_code, keywords)
        return _error_result(
            f"사람인 API HTTP 오류: {e.response.status_code}", safe_error_detail(e), start=start
        )
    except (httpx.RequestError, json.JSONDecodeError) as e:
        logger.warning(
            "사람인 API 요청 실패: %s: %s (keywords=%r)",
            type(e).__name__,
            redact_secrets(e),
            keywords,
        )
        return _error_result(
            f"사람인 API 요청 실패: {type(e).__name__}", safe_error_detail(e), start=start
        )
    finally:
        release_call_slot("saramin")

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
