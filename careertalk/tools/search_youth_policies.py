"""
Tool 3: search_youth_policies
==============================
온통청년 OpenAPI 로 청년정책·지원금을 검색한다.

입력: 나이, 지역, 상황(재학/졸업/미취업)
출력: 매칭 정책 리스트 (정책명, 지원금액, 신청자격, 마감일, 신청링크)

API(공식 기본): https://www.youthcenter.go.kr/opi/youthPlcyList.do — 인증키 openApiVlak
API(대체 형식): https://www.youthcenter.go.kr/go/ythip/getPlcy — 인증키 apiKeyNm
YOUTH_API_ENDPOINT 환경변수로 전환. 특징: 무료, 실시간 갱신.

나이·지역·상황 필터는 API 응답의 후처리라서, 필터 통과분이 display 에 찰 때까지
다음 페이지를 최대 YOUTH_MAX_FETCH_PAGES(기본 3)장 이어서 가져온다.

API 키가 없거나 MOCK_MODE=true 면 샘플 데이터를 반환한다.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
from typing import Any

import httpx

from .common import (
    DailyQuotaExceeded,
    acquire_call_slot,
    cache_get,
    cache_set,
    consume_daily_quota,
    env_ttl,
    external_api_timeout,
    get_youth_key,
    is_mock_mode,
    live_api_enabled,
    make_cache_key,
    rate_limit_exceeded,
    redact_secrets,
    release_call_slot,
    response_cache_enabled,
    safe_error_detail,
)
from .formatters import policy_cards

logger = logging.getLogger("careertalk.search_youth_policies")
_KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")

# 공식 공개 문서는 youthPlcyList.do/openApiVlak를 안내한다. getPlcy 형식도
# 파서 호환을 위해 유지하되 YOUTH_API_ENDPOINT를 명시했을 때만 사용한다.
YOUTH_ENDPOINT_OFFICIAL = "https://www.youthcenter.go.kr/opi/youthPlcyList.do"
YOUTH_ENDPOINT_ALTERNATE = "https://www.youthcenter.go.kr/go/ythip/getPlcy"


def get_youth_endpoint() -> str:
    return (os.getenv("YOUTH_API_ENDPOINT") or YOUTH_ENDPOINT_OFFICIAL).strip() or YOUTH_ENDPOINT_OFFICIAL


# ──────────────────────────────────────────────
# Mock 데이터
# ──────────────────────────────────────────────
_MOCK_POLICIES: list[dict[str, Any]] = [
    {
        "policy_id": "plcy-001",
        "policy_name": "청년 구직활동 지원금",
        "policy_number": "2025-청년-001",
        "support_amount": "월 30만원 (최대 6개월)",
        "eligibility": "18~34세 미취업 청년, 월 소득 200만원 이하",
        "category": "취업지원",
        "region": "전국",
        "application_period": "2026-07-01 ~ 2026-12-31",
        "deadline": "2026-12-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/001",
        "agency": "고용노동부",
        "description": "구직활동을 하는 미취업 청년에게 취업준비 비용을 지원합니다.",
        "_min_age": 18,
        "_max_age": 34,
        "_situations": ["미취업", "구직", "졸업", "취업준비"],
    },
    {
        "policy_id": "plcy-002",
        "policy_name": "청년 도전지원 사업",
        "policy_number": "2025-청년-002",
        "support_amount": "월 50만원 (최대 12개월)",
        "eligibility": "18~39세, 중소기업 취업자 또는 구직자",
        "category": "취업지원",
        "region": "전국",
        "application_period": "2026-06-15 ~ 2026-11-30",
        "deadline": "2026-11-30",
        "application_url": "https://www.youthcenter.go.kr/plcy/002",
        "agency": "고용노동부",
        "description": "청년의 중소기업 취업을 유도하기 위해 소득을 지원합니다.",
        "_min_age": 18,
        "_max_age": 39,
        "_situations": ["미취업", "구직단념", "쉬었음", "장기미취업", "구직"],
    },
    {
        "policy_id": "plcy-003",
        "policy_name": "서울청년수당",
        "policy_number": "2025-서울-003",
        "support_amount": "월 30만원 (최대 6개월)",
        "eligibility": "만 19~34세 서울거주 미취업 청년, 가구 소득 120분위 이하",
        "category": "생활안정",
        "region": "서울",
        "application_period": "2026-07-01 ~ 2026-08-31",
        "deadline": "2026-08-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/003",
        "agency": "서울특별시",
        "description": "서울시 거주 미취업 청년의 생활안정과 구직활동을 지원합니다.",
        "_min_age": 19,
        "_max_age": 34,
        "_situations": ["미취업", "구직", "졸업", "취업준비"],
    },
    {
        "policy_id": "plcy-004",
        "policy_name": "청년 주거안정 월세지원",
        "policy_number": "2025-주거-004",
        "support_amount": "월 최대 20만원 (최대 12개월)",
        "eligibility": "만 19~34세 무주택 청년, 월 소득 70만원 이하",
        "category": "주거지원",
        "region": "전국",
        "application_period": "2026-07-15 ~ 2026-10-31",
        "deadline": "2026-10-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/004",
        "agency": "국토교통부",
        "description": "무주택 청년의 주거안정을 위해 월세를 지원합니다.",
        "_min_age": 19,
        "_max_age": 34,
        "_situations": ["주거", "독립", "자취", "재학생", "미취업", "취업"],
    },
    {
        "policy_id": "plcy-005",
        "policy_name": "청년 창업지원금 (초기 창업 패키지)",
        "policy_number": "2025-창업-005",
        "support_amount": "최대 1억원 (사업화 자금)",
        "eligibility": "만 20~39세 예비 창업자, 창업 3년 이내 기업",
        "category": "창업지원",
        "region": "전국",
        "application_period": "2026-06-01 ~ 2026-09-30",
        "deadline": "2026-09-30",
        "application_url": "https://www.youthcenter.go.kr/plcy/005",
        "agency": "중소벤처기업부",
        "description": "청년 창업가의 초기 사업화 자금을 지원합니다.",
        "_min_age": 20,
        "_max_age": 39,
        "_situations": ["창업", "예비창업", "사업", "프리랜서"],
    },
    {
        "policy_id": "plcy-006",
        "policy_name": "청년 디지털 역량 강화 교육",
        "policy_number": "2025-교육-006",
        "support_amount": "교육 무료 + 훈련장려금 월 30만원",
        "eligibility": "만 18~39세 미취업 청년, 디지털 직무 희망자",
        "category": "교육지원",
        "region": "전국",
        "application_period": "2026-07-01 ~ 2026-12-31",
        "deadline": "2026-12-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/006",
        "agency": "과학기술정보통신부",
        "description": "AI, 빅데이터, 클라우드 등 디지털 직무 역량을 무료로 교육합니다.",
        "_min_age": 18,
        "_max_age": 39,
        "_situations": ["미취업", "구직", "졸업", "재학생", "직무전환", "교육"],
    },
    {
        "policy_id": "plcy-007",
        "policy_name": "부산 청년 일경험 디딤돌",
        "policy_number": "2026-부산-007",
        "support_amount": "3개월 일경험 + 월 활동수당",
        "eligibility": "부산 거주 18~34세 미취업·졸업예정 청년",
        "category": "일경험",
        "region": "부산",
        "application_period": "상시 모집 회차별 확인",
        "deadline": "2026-10-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/007",
        "agency": "부산광역시",
        "description": "지역 기업 프로젝트를 통해 첫 직무 경험과 멘토링을 제공하는 데모 정책입니다.",
        "_min_age": 18,
        "_max_age": 34,
        "_situations": ["미취업", "졸업", "졸업예정", "경력없음", "일경험"],
    },
    {
        "policy_id": "plcy-008",
        "policy_name": "경기 청년 면접 준비 지원",
        "policy_number": "2026-경기-008",
        "support_amount": "면접비·정장 대여·모의면접 지원",
        "eligibility": "경기도 거주 18~39세 구직 청년",
        "category": "취업지원",
        "region": "경기",
        "application_period": "분기별 모집",
        "deadline": "2026-11-15",
        "application_url": "https://www.youthcenter.go.kr/plcy/008",
        "agency": "경기도",
        "description": "면접 비용과 준비 부담을 낮추는 통합형 데모 지원입니다.",
        "_min_age": 18,
        "_max_age": 39,
        "_situations": ["미취업", "구직", "면접", "졸업", "이직"],
    },
    {
        "policy_id": "plcy-009",
        "policy_name": "재학생 직무체험 프로젝트",
        "policy_number": "2026-교육-009",
        "support_amount": "8주 프로젝트 + 멘토링 + 활동비",
        "eligibility": "18~34세 대학·전문대 재학생 및 졸업예정자",
        "category": "일경험",
        "region": "전국",
        "application_period": "학기별 모집",
        "deadline": "2026-09-20",
        "application_url": "https://www.youthcenter.go.kr/plcy/009",
        "agency": "교육부",
        "description": "전공과 무관하게 기업 과제를 경험하고 결과물을 포트폴리오로 남기는 데모 정책입니다.",
        "_min_age": 18,
        "_max_age": 34,
        "_situations": ["재학생", "대학생", "졸업예정", "경력없음", "일경험"],
    },
    {
        "policy_id": "plcy-010",
        "policy_name": "청년 프리랜서 계약·세무 상담",
        "policy_number": "2026-권익-010",
        "support_amount": "계약서 검토 및 기초 세무상담 무료",
        "eligibility": "19~39세 프리랜서·플랫폼 노동 청년",
        "category": "권익지원",
        "region": "전국",
        "application_period": "상시 상담",
        "deadline": "2026-12-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/010",
        "agency": "청년권익지원센터",
        "description": "불공정 계약과 대금 지연을 예방하도록 전문가 상담을 연결하는 데모 정책입니다.",
        "_min_age": 19,
        "_max_age": 39,
        "_situations": ["프리랜서", "플랫폼", "계약", "세무", "부업"],
    },
    {
        "policy_id": "plcy-011",
        "policy_name": "청년 마음건강 회복 바우처",
        "policy_number": "2026-마음-011",
        "support_amount": "초기 상담 및 전문상담 회기 지원",
        "eligibility": "19~34세 정서적 어려움을 겪는 청년",
        "category": "마음건강",
        "region": "전국",
        "application_period": "지역별 예산 소진 시까지",
        "deadline": "2026-12-15",
        "application_url": "https://www.youthcenter.go.kr/plcy/011",
        "agency": "보건복지부",
        "description": "취업 불안, 번아웃, 고립감에 대한 전문 상담 접근성을 높이는 데모 정책입니다.",
        "_min_age": 19,
        "_max_age": 34,
        "_situations": ["불안", "우울", "번아웃", "고립", "마음", "미취업"],
    },
    {
        "policy_id": "plcy-012",
        "policy_name": "가족돌봄청년 생활·진로 통합지원",
        "policy_number": "2026-돌봄-012",
        "support_amount": "돌봄비 상담 + 진로 멘토링 + 지역 서비스 연계",
        "eligibility": "13~39세 가족돌봄 부담이 있는 청년",
        "category": "생활안정",
        "region": "전국",
        "application_period": "상시 발굴·신청",
        "deadline": "2026-12-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/012",
        "agency": "보건복지부",
        "description": "가족 돌봄 때문에 학업·취업을 미루는 청년을 지역 지원체계와 연결하는 데모 정책입니다.",
        "_min_age": 13,
        "_max_age": 39,
        "_situations": ["가족돌봄", "돌봄", "재학생", "미취업", "휴학", "생활"],
    },
    {
        "policy_id": "plcy-013",
        "policy_name": "청년 금융·채무 첫 상담",
        "policy_number": "2026-금융-013",
        "support_amount": "재무 진단·채무조정 제도 안내 무료",
        "eligibility": "19~39세 금융 고민이 있는 청년",
        "category": "금융지원",
        "region": "전국",
        "application_period": "상시 상담",
        "deadline": "2026-12-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/013",
        "agency": "서민금융진흥원",
        "description": "대출, 연체, 생활비 고민을 공공 상담기관과 연결하는 데모 정책입니다.",
        "_min_age": 19,
        "_max_age": 39,
        "_situations": ["대출", "빚", "채무", "금융", "생활비", "미취업"],
    },
    {
        "policy_id": "plcy-014",
        "policy_name": "장애청년 맞춤형 취업 동행",
        "policy_number": "2026-포용-014",
        "support_amount": "직무평가·보조공학·면접 동행 지원",
        "eligibility": "18~39세 장애 청년 구직자",
        "category": "취업지원",
        "region": "전국",
        "application_period": "상시 접수",
        "deadline": "2026-12-31",
        "application_url": "https://www.youthcenter.go.kr/plcy/014",
        "agency": "한국장애인고용공단",
        "description": "개인의 접근성 요구를 반영해 구직 준비와 사업장 연결을 돕는 데모 정책입니다.",
        "_min_age": 18,
        "_max_age": 39,
        "_situations": ["장애", "접근성", "미취업", "구직", "취업"],
    },
]


def _mock_search(
    age: int | None, region: str, situation: str, display: int
) -> dict[str, Any]:
    """Mock 모드 — 간단한 필터링 후 반환."""
    today = datetime.datetime.now(_KST).date()
    demo_policies: list[dict[str, Any]] = []
    for index, item in enumerate(_MOCK_POLICIES):
        policy = dict(item)
        policy["deadline"] = (today + datetime.timedelta(days=30 + index * 14)).isoformat()
        policy["application_url"] = "https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch"
        policy["is_demo"] = True
        demo_policies.append(policy)

    filtered = _filter_policies(
        demo_policies,
        age=age,
        region=region,
        situation=situation,
    )

    strict_count = len(filtered)
    relaxed_filters: list[str] = []
    if not filtered and situation:
        filtered = _filter_policies(demo_policies, age=age, region=region, situation="")
        relaxed_filters.append("상황 조건")
    if not filtered and region:
        filtered = _filter_policies(demo_policies, age=age, region="", situation="")
        relaxed_filters.append("지역 조건")

    policies = [_strip_internal_fields(dict(item)) for item in filtered[:display]]
    if relaxed_filters:
        for policy in policies:
            policy["match_note"] = "정확히 일치하는 데모 정책이 없어 조건을 넓힌 참고 결과입니다."
    return {
        "total": len(policies),
        "display": len(policies),
        "pageIndex": 1,
        "source": "mock",
        "demo_data": True,
        "exact_match_count": strict_count,
        "relaxed_filters": relaxed_filters,
        "policies": policies,
        "kakao_cards": policy_cards(policies),
        "quick_replies": ["취업 지원만", "주거 지원만", "신청 준비물", "내 지역 넓혀 보기", "7일 계획 만들기"],
        "message": (
            f"[Mock 모드] 조건에 맞는 데모 정책 {strict_count}건"
            if strict_count
            else f"[Mock 모드] 조건을 넓힌 참고 정책 {len(policies)}건"
        ) + " (API 연결 시 자격·마감 실시간 확인)",
    }


def _pick(item: dict[str, Any], *keys: str, default: str = "") -> str:
    """여러 후보 키 중 처음으로 값이 있는 것을 반환 (v2·legacy 필드명 모두 대응)."""
    for k in keys:
        v = item.get(k)
        if v not in (None, "", "null", "None"):
            return str(v)
    return default


def _bounded_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    """문자열/None 입력도 안전하게 정수 범위로 보정."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_date(s: str) -> str:
    """다양한 날짜 표기를 'YYYY-MM-DD' 로. 범위면 마지막(종료) 날짜 채택. 실패 시 ''."""
    if not s:
        return ""
    digits = re.findall(r"\d{8}", str(s))
    if digits:
        d = digits[-1]
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    m = re.findall(r"\d{4}-\d{2}-\d{2}", str(s))
    return m[-1] if m else ""


def _parse_youth_response(data: Any) -> list[dict[str, Any]]:
    """온통청년 응답(JSON v2 / legacy / XML 변환)을 표준 형태로 변환.

    v2:    { "result": { "youthPolicyList": [...] } }  (현행)
    legacy:{ "youthPolicy": [...] }                    (구)
    필드명이 세대마다 다르므로 _pick 으로 후보 키를 폭넓게 매핑한다.
    """
    items: Any = []
    if isinstance(data, dict):
        root = data.get("result", data)
        if isinstance(root, dict):
            items = (
                root.get("youthPolicyList")
                or root.get("youthPolicy")
                or root.get("policies")
                or []
            )
        elif isinstance(root, list):
            items = root
    elif isinstance(data, list):
        items = data
    if isinstance(items, dict):
        items = [items]

    parsed: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        period = _pick(item, "aplyYmd", "rqutPrdCn", "bizApplYmd", "applicationPeriod")
        if not period:
            bgn = _pick(item, "bizPrdBgngYmd")
            end = _pick(item, "bizPrdEndYmd")
            period = f"{bgn} ~ {end}".strip(" ~") if (bgn or end) else ""
        deadline = _normalize_date(
            _pick(item, "bizPrdEndYmd", "aplyEndYmd") or period
        )
        parsed.append({
            "policy_id": _pick(item, "plcyNo", "polyBizId", "bizId", "policyId"),
            "policy_name": _pick(item, "plcyNm", "polyBizSjnm", "policyName"),
            "policy_number": _pick(item, "plcyNo", "polyBizId"),
            "support_amount": _pick(item, "plcySprtCn", "sprtSclCnt", "sporCn",
                                    "sprtCn", "supportContent"),
            "eligibility": _build_eligibility(item),
            "category": _pick(item, "lclsfNm", "mclsfNm", "polyBizTy", "categoryName"),
            "region": _pick(item, "rgnNm", "zipCd", "sprtRgnNm",
                            "supportRegion", default="전국"),
            "application_period": period,
            "deadline": deadline,
            "application_url": _pick(item, "aplyUrlAddr", "rqutUrl", "refUrl",
                                     "refUrlAddr1", "applicationUrl"),
            "agency": _pick(item, "sprvsnInstCdNm", "operInstCdNm", "cnsgNmor",
                            "srchOrgNm", "agencyName"),
            "description": _pick(item, "plcyExplnCn", "polyItcnCn", "description"),
            "_min_age": _pick(item, "sprtTrgtMinAge"),
            "_max_age": _pick(item, "sprtTrgtMaxAge"),
        })
    return parsed


def _matches_age(policy: dict[str, Any], age: int | None) -> bool:
    if age is None:
        return True
    try:
        min_age = int(policy.get("_min_age") or 0)
    except (TypeError, ValueError):
        min_age = 0
    try:
        max_age = int(policy.get("_max_age") or 999)
    except (TypeError, ValueError):
        max_age = 999
    return min_age <= age <= max_age


def _strip_internal_fields(policy: dict[str, Any]) -> dict[str, Any]:
    policy.pop("_min_age", None)
    policy.pop("_max_age", None)
    policy.pop("_situations", None)
    return policy


_SITUATION_ALIASES: dict[str, tuple[str, ...]] = {
    "미취업": ("미취업", "구직", "취업준비", "구직단념", "쉬었음", "장기미취업"),
    "재학": ("재학", "재학생", "대학생", "휴학", "졸업예정"),
    "졸업": ("졸업", "졸업예정", "취업준비", "미취업"),
    "이직": ("이직", "직무전환", "재직", "면접"),
    "프리랜서": ("프리랜서", "플랫폼", "부업", "계약", "세무"),
    "창업": ("창업", "예비창업", "사업"),
    "주거": ("주거", "월세", "자취", "독립", "무주택"),
    "돌봄": ("가족돌봄", "돌봄", "생활"),
}


def _situation_terms(situation: str) -> set[str]:
    query = str(situation or "").lower().replace(" ", "")
    if not query:
        return set()
    terms = {query}
    for category, aliases in _SITUATION_ALIASES.items():
        normalized_aliases = {alias.lower().replace(" ", "") for alias in aliases}
        if category in query or any(alias in query for alias in normalized_aliases):
            terms.update(normalized_aliases)
    return terms


def _filter_policies(
    policies: list[dict[str, Any]],
    *,
    age: int | None,
    region: str,
    situation: str,
) -> list[dict[str, Any]]:
    """API가 넓게 돌려준 결과를 사용자의 조건으로 한 번 더 좁힌다."""
    filtered: list[dict[str, Any]] = []
    for policy in policies:
        if not _matches_age(policy, age):
            continue
        if region and region not in ("전국", "미지정"):
            policy_region = str(policy.get("region") or "")
            if region not in policy_region and "전국" not in policy_region:
                continue
        if situation:
            haystack = " ".join(
                str(policy.get(k) or "")
                for k in ("policy_name", "category", "eligibility", "description", "support_amount", "_situations")
            ).lower().replace(" ", "")
            if not any(term in haystack for term in _situation_terms(situation)):
                continue
        filtered.append(policy)
    return filtered


def _api_total(data: Any) -> int | None:
    """API 응답에서 전체 건수(totNum 등)를 최대한 찾아본다. 없으면 None."""
    if not isinstance(data, dict):
        return None
    root = data.get("result", data)
    if not isinstance(root, dict):
        return None
    paging = root.get("pagging") or root.get("paging") or {}
    sources = [paging, root] if isinstance(paging, dict) else [root]
    for source in sources:
        for key in ("totNum", "totCnt", "totalCnt", "totalCount"):
            try:
                value = int(source.get(key))
            except (TypeError, ValueError):
                continue
            return value
    return None


def _max_fetch_pages() -> int:
    return _bounded_int(os.getenv("YOUTH_MAX_FETCH_PAGES"), 3, 1, 10)


async def _collect_filtered(
    fetch_page,
    *,
    age: int | None,
    region: str,
    situation: str,
    display: int,
    page_index: int,
    max_pages: int,
) -> tuple[list[dict[str, Any]], int | None, int]:
    """
    후처리 필터 통과분이 display 에 찰 때까지 연속 페이지를 가져온다.

    fetch_page(page) -> (파싱된 정책 리스트, api_total|None). 예외를 던질 수 있다.
    첫 페이지 예외는 그대로 전파(호출측이 error 응답으로 변환),
    이후 페이지 예외·레이트리밋은 지금까지 모은 부분 결과로 마감한다.

    Returns: (필터 통과 정책 리스트, api_total, 실제 가져온 페이지 수)
    """
    collected: list[dict[str, Any]] = []
    api_total: int | None = None
    pages_fetched = 0
    page = page_index

    while len(collected) < display and pages_fetched < max_pages:
        if pages_fetched > 0 and rate_limit_exceeded("external"):
            logger.warning("추가 페이지 조회가 레이트리밋에 걸려 부분 결과로 반환 (page=%d)", page)
            break
        try:
            items, total = await fetch_page(page)
        except DailyQuotaExceeded:
            raise
        except Exception:
            if pages_fetched == 0:
                raise
            logger.warning("추가 페이지 조회 실패 — 부분 결과로 반환 (page=%d)", page, exc_info=True)
            break
        if api_total is None:
            api_total = total
        if not items:
            break
        collected.extend(
            _filter_policies(items, age=age, region=region, situation=situation)
        )
        pages_fetched += 1
        page += 1
        if len(items) < display:
            # 마지막 페이지 (요청 크기보다 적게 반환됨)
            break

    return collected, api_total, pages_fetched


def _error_result(error: str, detail: str, *, page_index: int = 1) -> dict[str, Any]:
    return {
        "error": error,
        "detail": detail,
        "total": 0,
        "display": 0,
        "pageIndex": page_index,
        "source": "youthcenter",
        "policies": [],
        "kakao_cards": [],
        "message": error,
    }


def _build_eligibility(item: dict[str, Any]) -> str:
    """신청자격(연령·소득·추가조건)을 조합해서 생성."""
    min_age = _pick(item, "sprtTrgtMinAge")
    max_age = _pick(item, "sprtTrgtMaxAge")
    if min_age or max_age:
        age_part = f"{min_age or '0'}~{max_age or '제한없음'}세"
    else:
        age_part = _pick(item, "ageInfo")
    income_part = _pick(item, "earnEtcCn", "incomeInfo", "incomeCn", "earnCndSeCd")
    extra = _pick(item, "addAplyQlfcCndCn")
    parts = [p for p in [age_part, income_part, extra] if p]
    return " / ".join(parts) if parts else "상세 페이지 참조"


async def search_youth_policies(
    age: int | None = None,
    region: str = "",
    situation: str = "",
    display: int = 10,
    page_index: int = 1,
) -> dict[str, Any]:
    """
    청년정책·지원금을 검색합니다. (온통청년 OpenAPI)

    Args:
        age: 나이 (예: 24). 미지정 시 전체 연령.
        region: 지역 (예: "서울", "부산", "전국")
        situation: 상황 (예: "재학", "졸업", "미취업")
        display: 페이지당 결과 수 (기본 10)
        page_index: 페이지 번호 (1부터)

    Returns:
        매칭 정책 리스트 (정책명, 지원금액, 신청자격, 마감일, 신청링크)
    """
    raw_age = age
    age = _optional_int(age)
    region = str(region or "").strip()
    situation = str(situation or "").strip()
    display = _bounded_int(display, 10, 1, 10)
    page_index = _bounded_int(page_index, 1, 1, 10_000)
    if raw_age not in (None, "") and age is None:
        return _error_result("age는 정수여야 합니다.", "input_validation", page_index=page_index)
    if age is not None and not 0 <= age <= 120:
        return _error_result("age는 0~120 범위여야 합니다.", "input_validation", page_index=page_index)
    if len(region) > 80 or len(situation) > 100:
        return _error_result("region은 80자, situation은 100자 이하여야 합니다.", "input_validation", page_index=page_index)

    # ── 응답 캐시 조회 ──
    cache_on = response_cache_enabled()
    cache_key = make_cache_key(
        "search_youth_policies", age=age, region=region,
        situation=situation, display=display, page_index=page_index,
    )
    if cache_on:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    # ── Mock 모드 ──
    if is_mock_mode() or not live_api_enabled() or not get_youth_key():
        return _mock_search(age, region, situation, display)

    # ── 레이트리밋 (캐시 히트는 위에서 반환됨) ──
    limited = rate_limit_exceeded("external")
    if limited:
        return _error_result(limited, "rate_limited", page_index=page_index)

    denied = acquire_call_slot("youth")
    if denied:
        return _error_result(denied, "usage_guard", page_index=page_index)

    # ── 실제 API 호출 (엔드포인트 세대에 맞춰 파라미터 구성) ──
    endpoint = get_youth_endpoint()
    is_v2 = "getPlcy" in endpoint
    keyword = " ".join(
        s for s in [region if region and region != "전국" else "", situation] if s
    ).strip()

    def _build_params(page: int) -> dict[str, Any]:
        if is_v2:
            built: dict[str, Any] = {
                "apiKeyNm": get_youth_key(),
                "pageNum": page,
                "pageSize": display,
                "rtnType": "json",
            }
            if keyword:
                built["plcyKywdNm"] = keyword
        else:
            built = {
                "openApiVlak": get_youth_key(),
                "pageIndex": page,
                "display": display,
                "rtnType": "json",
            }
            if keyword:
                built["query"] = keyword
        return built

    try:
        async with httpx.AsyncClient(timeout=external_api_timeout()) as client:

            async def fetch_page(page: int) -> tuple[list[dict[str, Any]], int | None]:
                quota_error = consume_daily_quota("youth")
                if quota_error:
                    raise DailyQuotaExceeded(quota_error)
                resp = await client.get(endpoint, params=_build_params(page))
                resp.raise_for_status()
                # JSON 시도, 실패 시 XML 로 파싱
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    data = _xml_to_dict(resp.text)
                return _parse_youth_response(data), _api_total(data)

            # 후처리 필터로 건수가 줄어도 display 를 최대한 채우도록 연속 페이지 조회
            collected, api_total, pages_fetched = await asyncio.wait_for(
                _collect_filtered(
                    fetch_page,
                    age=age,
                    region=region,
                    situation=situation,
                    display=display,
                    page_index=page_index,
                    max_pages=_max_fetch_pages(),
                ),
                timeout=external_api_timeout(),
            )
    except DailyQuotaExceeded as e:
        return _error_result(str(e), "daily_quota", page_index=page_index)
    except asyncio.TimeoutError as e:
        logger.warning("온통청년 API 전체 요청 시간 초과 (region=%r, situation=%r)", region, situation)
        return _error_result(
            "온통청년 API 응답 시간이 초과되었습니다.", safe_error_detail(e), page_index=page_index
        )
    except httpx.HTTPStatusError as e:
        logger.warning("온통청년 API HTTP 오류: %s (region=%r, situation=%r)", e.response.status_code, region, situation)
        return _error_result(
            f"온통청년 API HTTP 오류: {e.response.status_code}", safe_error_detail(e), page_index=page_index
        )
    except httpx.RequestError as e:
        logger.warning(
            "온통청년 API 요청 실패: %s: %s (region=%r, situation=%r)",
            type(e).__name__,
            redact_secrets(e),
            region,
            situation,
        )
        return _error_result(
            f"온통청년 API 요청 실패: {type(e).__name__}", safe_error_detail(e), page_index=page_index
        )
    finally:
        release_call_slot("youth")

    has_more = len(collected) > display
    policies = [_strip_internal_fields(policy) for policy in collected[:display]]

    result = {
        "total": len(policies),
        "display": len(policies),
        "pageIndex": page_index,
        "fetched_pages": pages_fetched,
        "api_total": api_total,      # 필터 전 API 전체 건수 (모르면 None)
        "has_more": has_more,        # display 를 채우고도 남은 매칭이 있었는지
        "source": "youthcenter",
        "policies": policies,
        "kakao_cards": policy_cards(policies),
        "message": f"청년정책 {len(policies)}건 검색 완료 (페이지 {pages_fetched}장 조회)",
    }
    if cache_on:
        cache_set(cache_key, result, env_ttl("YOUTH_CACHE_TTL", 600))
    return result


def _xml_to_dict(xml_text: str) -> dict[str, Any]:
    """간단 XML → dict 변환 (온통청년 XML 응답 폴백)."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    def elem_to_dict(elem: ET.Element) -> Any:
        children = list(elem)
        if not children:
            return elem.text or ""
        result: dict[str, Any] = {}
        for child in children:
            tag = child.tag.split("}")[-1]  # namespace 제거
            val = elem_to_dict(child)
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(val)
            else:
                result[tag] = val
        return result

    return {root.tag.split("}")[-1]: elem_to_dict(root)}
