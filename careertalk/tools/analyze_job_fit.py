"""
Tool 2: analyze_job_fit
========================
LLM 으로 사용자 프로필 기반 직무 적합도 분석 및 추천.

입력: 관심분야, 학력, 성향 키워드, 선호 지역
출력: 추천 직무 TOP5 + 진입 경로 + 필요 스킬

LLM: OpenAI(gpt-4o-mini). 키가 없으면 Mock 반환.
"""

from __future__ import annotations

import logging
from typing import Any

from .common import (
    cache_get,
    cache_set,
    call_llm,
    env_ttl,
    get_llm_provider,
    is_mock_mode,
    make_cache_key,
    parse_json_object,
    rate_limit_exceeded,
    response_cache_enabled,
)
from .formatters import career_cards

logger = logging.getLogger("careertalk.analyze_job_fit")


_SYSTEM_PROMPT = """\
당신은 청년 진로 컨설턴트입니다. 사용자의 관심분야·학력·성향 키워드·선호 지역을 입력받아
적합한 직무 TOP5를 추천하고, 각 직무별 진입 경로와 필요 스킬을 제시합니다.

[출력 형식 — 반드시 아래 JSON 스키마에 맞춰 한국어로 응답]
{
  "recommended_jobs": [
    {
      "rank": 1,
      "job_title": "직무명",
      "fit_score": 92,
      "reason": "이 직무가 적합한 이유 (1~2문장)",
      "entry_path": "진입 경로 (예: '컴퓨터공학 학위 → 코딩부트캠프 → 신입 개발자')",
      "required_skills": ["필수 스킬1", "필수 스킬2"],
      "preferred_skills": ["우대 스킬1"],
      "salary_band": "신입 연봉 밴드 (예: 3,000~4,500만원)",
      "growth_outlook": "성장 전망 (1문장)"
    }
  ],
  "overall_summary": "종합 진로 조언 (2~3문장)",
  "next_actions": ["즉시 실행할 수 있는 다음 단계 1", "다음 단계 2", "다음 단계 3"]
}

- fit_score 는 0~100 사이 정수.
- recommended_jobs 는 정확히 5개.
- 모든 텍스트는 한국어.
"""


def _job_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:5]


def _mock_analysis(
    interests: str, education: str, tendencies: str, preferred_location: str
) -> dict[str, Any]:
    """LLM 키가 없을 때 반환하는 Mock 분석 결과."""
    interest_lower = interests.lower()

    if any(k in interest_lower for k in ("it", "개발", "코딩", "프로그래밍", "소프트웨어")):
        jobs = [
            {"rank": 1, "job_title": "백엔드 개발자", "fit_score": 92,
             "reason": "논리적 사고를 요구하는 분야로 분석력이 뛰어난 분에게 적합.",
             "entry_path": "컴퓨터공학 학위 → 코딩 부트캠프(3개월) → 신입 백엔드 개발자",
             "required_skills": ["Python/Java", "SQL", "웹 프레임워크"],
             "preferred_skills": ["AWS/GCP", "Docker"],
             "salary_band": "3,200~4,500만원 (신입)",
             "growth_outlook": "AI 인프라 확대로 백엔드 수요 지속 증가"},
            {"rank": 2, "job_title": "프론트엔드 개발자", "fit_score": 85,
             "reason": "UI/UX 에 관심이 있다면 사용자 경험을 직접 설계하는 직무.",
             "entry_path": "HTML/CSS/JS 독학 → React 실습 → 신입 프론트엔드",
             "required_skills": ["JavaScript", "React/Vue", "HTML/CSS"],
             "preferred_skills": ["TypeScript", "Next.js"],
             "salary_band": "3,000~4,200만원 (신입)",
             "growth_outlook": "웹 서비스 확장으로 안정적 수요"},
            {"rank": 3, "job_title": "데이터 분석가", "fit_score": 80,
             "reason": "데이터 기반 의사결정에 관심이 있다면 추천.",
             "entry_path": "Python/SQL 학습 → 개인 프로젝트 → 신입 데이터 분석가",
             "required_skills": ["Python", "SQL", "데이터 시각화"],
             "preferred_skills": ["Pandas", "Tableau"],
             "salary_band": "3,000~4,000만원 (신입)",
             "growth_outlook": "데이터 기반 조직 확산으로 수요 증가"},
            {"rank": 4, "job_title": "데브옵스 엔지니어", "fit_score": 72,
             "reason": "인프라 자동화에 관심이 있다면 성장성 높은 분야.",
             "entry_path": "Linux 기초 → AWS 자격증 → 신입 데브옵스",
             "required_skills": ["Linux", "AWS", "CI/CD"],
             "preferred_skills": ["Kubernetes", "Terraform"],
             "salary_band": "3,500~5,000만원 (신입)",
             "growth_outlook": "클라우드 전환 가속화로 인재 부족 심화"},
            {"rank": 5, "job_title": "AI/ML 엔지니어", "fit_score": 68,
             "reason": "석사 이상 또는 수학/통계 배경이 있다면 진입 가능.",
             "entry_path": "대학원(석사) → Kaggle 대회 → 신입 ML 엔지니어",
             "required_skills": ["Python", "PyTorch", "수학/통계"],
             "preferred_skills": ["NLP", "LLM 파인튜닝"],
             "salary_band": "4,000~6,000만원 (신입)",
             "growth_outlook": "AI 산업 전면 확대로 폭발적 수요"},
        ]
    else:
        jobs = [
            {"rank": 1, "job_title": "마케팅 기획자", "fit_score": 88,
             "reason": "트렌드에 민감하고 소통을 좋아하는 성향에 적합.",
             "entry_path": "마케팅 학위 → 인턴십 → 신입 마케팅 기획자",
             "required_skills": ["데이터 분석", "콘텐츠 기획", "SNS 운영"],
             "preferred_skills": ["GA", "Python 기초"],
             "salary_band": "2,800~3,800만원 (신입)",
             "growth_outlook": "디지털 마케팅 전환으로 수요 안정"},
            {"rank": 2, "job_title": "콘텐츠 에디터", "fit_score": 82,
             "reason": "글쓰기와 기획력을 활용할 수 있는 직무.",
             "entry_path": "블로그/포트폴리오 구축 → 신입 에디터",
             "required_skills": ["카피라이팅", "콘텐츠 기획", "SEO 기초"],
             "preferred_skills": ["영상 편집", "디자인 툴"],
             "salary_band": "2,700~3,500만원 (신입)",
             "growth_outlook": "콘텐츠 마케팅 확대로 수요 증가"},
            {"rank": 3, "job_title": "데이터 분석가", "fit_score": 76,
             "reason": "데이터 기반 인사이트 도출에 관심이 있다면 추천.",
             "entry_path": "Python/SQL 학습 → 개인 프로젝트 → 신입 데이터 분석가",
             "required_skills": ["Python", "SQL", "데이터 시각화"],
             "preferred_skills": ["Pandas", "Tableau"],
             "salary_band": "3,000~4,000만원 (신입)",
             "growth_outlook": "데이터 기반 조직 확산으로 수요 증가"},
            {"rank": 4, "job_title": "UX 리서처", "fit_score": 70,
             "reason": "사용자 행동 분석에 관심이 있다면 추천.",
             "entry_path": "UX 기초 학습 → 포트폴리오 → 신입 UX 리서처",
             "required_skills": ["사용자 인터뷰", "데이터 분석", "프로토타이핑"],
             "preferred_skills": ["Figma", "디자인 씽킹"],
             "salary_band": "3,000~4,200만원 (신입)",
             "growth_outlook": "디지털 제품 고도화로 수요 증가"},
            {"rank": 5, "job_title": "CS 매니저", "fit_score": 65,
             "reason": "고객 응대와 문제 해결에 강점이 있다면 적합.",
             "entry_path": "인턴십 → 신입 CS 매니저",
             "required_skills": ["커뮤니케이션", "CRM", "데이터 분석 기초"],
             "preferred_skills": ["Zendesk", "SQL 기초"],
             "salary_band": "2,700~3,500만원 (신입)",
             "growth_outlook": "CS 품질 차별화 트렌드로 수요 안정"},
        ]

    return {
        "source": "mock",
        "input": {
            "interests": interests, "education": education,
            "tendencies": tendencies, "preferred_location": preferred_location,
        },
        "recommended_jobs": jobs,
        "kakao_cards": career_cards(jobs),
        "overall_summary": (
            f"'{interests}' 분야와 '{tendencies}' 성향을 고려할 때, "
            f"데이터 기반 의사결정과 창의적 문제해결을 결합한 직무가 적합해 보입니다. "
            f"단기적으로는 필수 스킬을 익히고 개인 프로젝트를 구축하는 것을 권장합니다."
        ),
        "next_actions": [
            "추천 직무 1~2위 중 하나를 선택해 필수 스킬 학습 계획 수립",
            "관심 분야 관련 온라인 코스(인프런/코세라) 1개 수강 시작",
            "학습 내용을 바탕으로 간단한 개인 프로젝트 or 포트폴리오 제작",
        ],
        "message": "[Mock 모드] LLM API 키 설정 시 맞춤형 분석 결과 제공",
    }


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    """LLM 응답에서 JSON 블록 추출."""
    return parse_json_object(text)


async def analyze_job_fit(
    interests: str,
    education: str = "",
    tendencies: str = "",
    preferred_location: str = "",
) -> dict[str, Any]:
    """
    AI 진로 적성 진단 및 직무 추천.

    Args:
        interests: 관심 분야 (예: "IT 개발", "마케팅", "디자인")
        education: 학력 (예: "대학교 4년 졸업 예정", "전문대 졸업", "고졸")
        tendencies: 성향 키워드 (예: "논리적, 분석적, 협업 선호")
        preferred_location: 선호 지역 (예: "서울", "부산", "원격")

    Returns:
        추천 직무 TOP5 + 진입 경로 + 필요 스킬 + 종합 조언
    """
    interests = str(interests or "").strip()
    education = str(education or "").strip()
    tendencies = str(tendencies or "").strip()
    preferred_location = str(preferred_location or "").strip()
    if not interests:
        return {
            "error": "interests 가 비어있습니다. 관심 분야를 입력해주세요.",
            "recommended_jobs": [],
            "overall_summary": "",
            "next_actions": [],
            "kakao_cards": [],
        }

    # ── 응답 캐시 조회 ──
    cache_on = response_cache_enabled()
    cache_key = make_cache_key(
        "analyze_job_fit", interests=interests, education=education,
        tendencies=tendencies, preferred_location=preferred_location,
    )
    if cache_on:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    # ── Mock 모드 ──
    if is_mock_mode() or not get_llm_provider():
        return _mock_analysis(interests, education, tendencies, preferred_location)

    # ── 레이트리밋 (LLM 비용 보호 — 캐시 히트는 여기 오기 전에 반환됨) ──
    limited = rate_limit_exceeded("llm")
    if limited:
        return {
            "error": limited,
            "source": "rate_limited",
            "recommended_jobs": [],
            "overall_summary": "",
            "next_actions": [],
            "kakao_cards": [],
            "message": limited,
        }

    # ── LLM 호출 ──
    user_prompt = (
        f"[사용자 프로필]\n"
        f"- 관심분야: {interests}\n"
        f"- 학력: {education or '미지정'}\n"
        f"- 성향 키워드: {tendencies or '미지정'}\n"
        f"- 선호 지역: {preferred_location or '미지정'}\n\n"
        f"위 프로필을 기반으로 적합한 직무 TOP5를 추천하고, "
        f"각 직무별 진입 경로와 필요 스킬을 제시해주세요."
    )

    raw = await call_llm(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.4,
        max_tokens=1500,
        json_mode=True,
    )

    if not raw:
        return _mock_analysis(interests, education, tendencies, preferred_location)

    parsed = _parse_llm_json(raw)
    if not parsed:
        # JSON 파싱 실패 시 원문을 그대로 반환 — 일시 오류일 수 있으므로 캐시하지 않는다.
        logger.warning("LLM 응답 JSON 파싱 실패 (analyze_job_fit, len=%d)", len(raw))
        return {
            "source": "llm",
            "raw_response": raw,
            "recommended_jobs": [],
            "overall_summary": raw[:500],
            "next_actions": [],
            "kakao_cards": [],
            "message": "LLM 응답을 JSON 으로 파싱하지 못해 원문을 반환합니다.",
        }

    parsed["recommended_jobs"] = _job_list(parsed.get("recommended_jobs"))
    parsed["source"] = "llm"
    parsed["input"] = {
        "interests": interests, "education": education,
        "tendencies": tendencies, "preferred_location": preferred_location,
    }
    parsed.setdefault("message", "AI 진로 적성 분석 완료")
    parsed["kakao_cards"] = career_cards(parsed.get("recommended_jobs", []))

    # 성공 응답만 캐시 (실패 결과가 TTL 동안 고착되는 것 방지)
    if cache_on:
        cache_set(cache_key, parsed, env_ttl("LLM_CACHE_TTL", 3600))
    return parsed
