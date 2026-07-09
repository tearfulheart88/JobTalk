"""
Tool 3: search_youth_policies
==============================
온통청년 OpenAPI 로 청년정책·지원금을 검색한다.

입력: 나이, 지역, 상황(재학/졸업/미취업)
출력: 매칭 정책 리스트 (정책명, 지원금액, 신청자격, 마감일, 신청링크)

API(기본, v2): https://www.youthcenter.go.kr/go/ythip/getPlcy — 인증키 apiKeyNm
API(legacy):   https://www.youthcenter.go.kr/opi/youthPlcyList.do — 인증키 openApiVlak
YOUTH_API_ENDPOINT 환경변수로 전환. 특징: 무료, 실시간 갱신.

나이·지역·상황 필터는 API 응답의 후처리라서, 필터 통과분이 display 에 찰 때까지
다음 페이지를 최대 YOUTH_MAX_FETCH_PAGES(기본 3)장 이어서 가져온다.

API 키가 없거나 MOCK_MODE=true 면 샘플 데이터를 반환한다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

from .common import (
    cache_get,
    cache_set,
    env_ttl,
    get_youth_key,
    is_mock_mode,
    make_cache_key,
    rate_limit_exceeded,
    response_cache_enabled,
)
from .formatters import policy_cards

logger = logging.getLogger("careertalk.search_youth_policies")

# 온통청년 OpenAPI 는 세대가 둘이다:
#   - v2(현행, 공공데이터포털 15143273): /go/ythip/getPlcy, 인증키 apiKeyNm,
#     페이지 pageNum/pageSize, rtnType=json, 응답 result.youthPolicyList[]
#   - legacy(구): /opi/youthPlcyList.do, 인증키 openApiVlak, pageIndex/display
# 발급받은 키에 맞춰 YOUTH_API_ENDPOINT 환경변수로 전환 가능. 기본은 현행 v2.
YOUTH_ENDPOINT_V2 = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
YOUTH_ENDPOINT_LEGACY = "https://www.youthcenter.go.kr/opi/youthPlcyList.do"


def get_youth_endpoint() -> str:
    return (os.getenv("YOUTH_API_ENDPOINT") or YOUTH_ENDPOINT_V2).strip() or YOUTH_ENDPOINT_V2


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
    },
]


def _mock_search(
    age: int | None, region: str, situation: str, display: int
) -> dict[str, Any]:
    """Mock 모드 — 간단한 필터링 후 반환."""
    filtered = _filter_policies(
        list(_MOCK_POLICIES),
        age=age,
        region=region,
        situation=situation,
    )

    policies = filtered[:display]
    return {
        "total": len(policies),
        "display": len(policies),
        "pageIndex": 1,
        "source": "mock",
        "policies": policies,
        "kakao_cards": policy_cards(policies),
        "message": f"[Mock 모드] 청년정책 {len(policies)}건 검색 (실제 API 키 설정 시 실시간 데이터 반환)",
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
    return policy


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
                for k in ("policy_name", "category", "eligibility", "description", "support_amount")
            )
            if situation not in haystack:
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
    age = _optional_int(age)
    region = str(region or "").strip()
    situation = str(situation or "").strip()
    display = _bounded_int(display, 10, 1, 100)
    page_index = _bounded_int(page_index, 1, 1, 10_000)

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
    if is_mock_mode() or not get_youth_key():
        return _mock_search(age, region, situation, display)

    # ── 레이트리밋 (캐시 히트는 위에서 반환됨) ──
    limited = rate_limit_exceeded("external")
    if limited:
        return _error_result(limited, "rate_limited", page_index=page_index)

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
        async with httpx.AsyncClient(timeout=15.0) as client:

            async def fetch_page(page: int) -> tuple[list[dict[str, Any]], int | None]:
                resp = await client.get(endpoint, params=_build_params(page))
                resp.raise_for_status()
                # JSON 시도, 실패 시 XML 로 파싱
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    data = _xml_to_dict(resp.text)
                return _parse_youth_response(data), _api_total(data)

            # 후처리 필터로 건수가 줄어도 display 를 최대한 채우도록 연속 페이지 조회
            collected, api_total, pages_fetched = await _collect_filtered(
                fetch_page,
                age=age,
                region=region,
                situation=situation,
                display=display,
                page_index=page_index,
                max_pages=_max_fetch_pages(),
            )
    except httpx.HTTPStatusError as e:
        logger.warning("온통청년 API HTTP 오류: %s (region=%r, situation=%r)", e.response.status_code, region, situation)
        return _error_result(f"온통청년 API HTTP 오류: {e.response.status_code}", str(e), page_index=page_index)
    except httpx.RequestError as e:
        logger.warning("온통청년 API 요청 실패: %s: %s (region=%r, situation=%r)", type(e).__name__, e, region, situation)
        return _error_result(f"온통청년 API 요청 실패: {type(e).__name__}", str(e), page_index=page_index)

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
