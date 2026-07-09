"""
Tool 4: generate_resume_tip
============================
LLM 으로 자기소개서 첨삭 + 면접 예상질문 생성.

입력: 자소서 텍스트, 지원 직무, 회사명(선택)
출력: 첨삭본 + 예상 면접질문 5선 + 개선 포인트

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
from .formatters import coaching_cards

logger = logging.getLogger("careertalk.generate_resume_tip")

# 자소서 원문은 개인정보를 포함할 수 있으므로 LLM 전송 사실을 응답에 명시한다.
_PRIVACY_NOTICE = (
    "자소서 원문은 첨삭 생성을 위해 OpenAI API 로 전송됩니다. "
    "서버에는 영구 저장되지 않으며, 동일 입력 캐시는 최대 1시간 후 만료됩니다."
)


_SYSTEM_PROMPT = """\
당신은 전문 자기소개서 첨삭 컨설턴트입니다. 사용자가 제출한 자기소개서를 첨삭하고,
지원 직무에 맞는 예상 면접질문 5개를 생성하며, 개선 포인트를 제시합니다.

[출력 형식 — 반드시 아래 JSON 스키마에 맞춰 한국어로 응답]
{
  "edited_resume": "첨삭된 자기소개서 전문. 원본의 의미를 유지하면서 더 설득력 있게 다듬은 버전.",
  "editing_notes": ["수정 1: ...", "수정 2: ...", "수정 3: ..."],
  "expected_interview_questions": [
    {
      "question": "예상 면접 질문",
      "intent": "이 질문을 통해 면접관이 확인하려는 점",
      "suggested_answer_points": ["답변 포인트 1", "답변 포인트 2"]
    }
  ],
  "improvement_points": [
    {"section": "지원동기", "issue": "구체성 부족", "suggestion": "회사의 OOO 점을 구체적으로 언급하세요."}
  ],
  "overall_feedback": "종합 평가 (2~3문장)"
}

- expected_interview_questions 는 정확히 5개.
- editing_notes 는 3~5개.
- improvement_points 는 2~4개.
- 모든 텍스트는 한국어.
"""


def _list_of_dicts(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:limit]


def _mock_resume_tip(
    resume_text: str, target_job: str, company_name: str
) -> dict[str, Any]:
    """LLM 키가 없을 때 반환하는 Mock 결과."""
    # 원문을 간단히 다듬은 버전 (단순 줄바꿈 정리)
    edited = (
        resume_text.strip()
        .replace("\n\n\n", "\n\n")
        .replace("  ", " ")
    )
    if len(edited) < 50:
        edited = (
            f"[첨삭본] {target_job or '지원 직무'}에 지원하는 지원자의 자기소개서입니다.\n\n"
            + edited
        )

    result = {
        "source": "mock",
        "input": {
            "resume_text_length": len(resume_text),
            "target_job": target_job,
            "company_name": company_name,
        },
        "edited_resume": edited,
        "editing_notes": [
            "수정 1: 문단 구조를 지원동기→직무 적합성→포부 순으로 재배치",
            "수정 2: 추상적 표현('열심히 하겠습니다')을 구체적 경험으로 대체 권장",
            "수정 3: 회사명 언급 추가 — 'OOO의 비전과 제 역량이 시너지를 낼 수 있습니다'",
            "수정 4: 직무 키워드 2~3개를 자연스럽게 포함하도록 권장",
        ],
        "expected_interview_questions": [
            {
                "question": f"{target_job or '해당 직무'}에 지원한 동기가 무엇인가요?",
                "intent": "지원동기의 진정성과 직무 이해도 확인",
                "suggested_answer_points": [
                    "회사의 구체적 비전/제품 언급",
                    "본인의 경험과 직무의 연결점",
                    "입사 후 기여할 수 있는 점",
                ],
            },
            {
                "question": "본인의 강점 중 이 직무에 가장 도움이 되는 것은?",
                "intent": "직무 적합성과 자기 인식 검증",
                "suggested_answer_points": [
                    "강점 1가지 + 구체적 사례",
                    "강점이 직무에 미치는 영향 설명",
                ],
            },
            {
                "question": "가장 실패했던 경험과 그 교훈은?",
                "intent": "실패 대처 능력과 성장 마인드셋",
                "suggested_answer_points": [
                    "구체적 실패 상황 (STAR 기법)",
                    "원인 분석과 개선 노력",
                    "이후 성과로 증명",
                ],
            },
            {
                "question": f"{company_name or '우리 회사'}에서 어떤 성과를 만들고 싶나요?",
                "intent": "회사 이해도와 비전 부합성",
                "suggested_answer_points": [
                    "회사 사업/비전 언급",
                    "단기+장기 성과 목표",
                    "본인의 구체적 기여 방법",
                ],
            },
            {
                "question": "마지막으로 하고 싶은 말이 있다면?",
                "intent": "열의와 소통 능력 마지막 점검",
                "suggested_answer_points": [
                    "핵심 역량 1가지 재강조",
                    "입사 의지 표명",
                    "간결하고 인상적인 마무리",
                ],
            },
        ],
        "improvement_points": [
            {"section": "지원동기", "issue": "구체성 부족",
             "suggestion": "회사의 최근 뉴스/제품 1개를 언급하세요."},
            {"section": "직무 적합성", "issue": "역량 증빙 부족",
             "suggestion": "숫자/성과로 증빙 가능한 경험을 추가하세요."},
            {"section": "포부", "issue": "원론적 표현",
             "suggestion": "3년 뒤 구체적 목표를 제시하세요."},
        ],
        "overall_feedback": (
            f"[Mock 모드] 원문을 바탕으로 간단히 첨삭한 결과입니다. "
            f"LLM API 키 설정 시 맞춤형 심층 첨삭이 제공됩니다. "
            f"전반적으로 구체적 사례와 숫자 기반 성과를 보강하면 설득력이 크게 향상됩니다."
        ),
    }
    result["kakao_cards"] = coaching_cards(result)
    return result


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    """LLM 응답에서 JSON 블록 추출."""
    return parse_json_object(text)


async def generate_resume_tip(
    resume_text: str,
    target_job: str = "",
    company_name: str = "",
) -> dict[str, Any]:
    """
    자기소개서 첨삭 + 면접 예상질문 생성.

    Args:
        resume_text: 자소서 원문 텍스트
        target_job: 지원 직무 (예: "백엔드 개발자")
        company_name: 지원 회사명 (선택, 예: "(주)네이버")

    Returns:
        첨삭본 + 예상 면접질문 5선 + 개선 포인트 + 종합 평가
    """
    resume_text = str(resume_text or "")
    target_job = str(target_job or "").strip()
    company_name = str(company_name or "").strip()

    # 입력 검증
    if not resume_text or not resume_text.strip():
        return {
            "error": "resume_text 가 비어있습니다. 자소서 원문을 입력해주세요.",
            "edited_resume": "",
            "expected_interview_questions": [],
            "improvement_points": [],
            "kakao_cards": [],
        }

    # ── 응답 캐시 조회 ──
    cache_on = response_cache_enabled()
    cache_key = make_cache_key(
        "generate_resume_tip", resume_text=resume_text,
        target_job=target_job, company_name=company_name,
    )
    if cache_on:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    # ── Mock 모드 ──
    if is_mock_mode() or not get_llm_provider():
        return _mock_resume_tip(resume_text, target_job, company_name)

    # ── 레이트리밋 (LLM 비용 보호 — 캐시 히트는 여기 오기 전에 반환됨) ──
    limited = rate_limit_exceeded("llm")
    if limited:
        return {
            "error": limited,
            "source": "rate_limited",
            "edited_resume": "",
            "editing_notes": [],
            "expected_interview_questions": [],
            "improvement_points": [],
            "kakao_cards": [],
            "message": limited,
        }

    # ── LLM 호출 ──
    # 너무 긴 원문은 잘라서 전송 (토큰 절약)
    truncated = resume_text[:4000]
    if len(resume_text) > 4000:
        truncated += "\n\n[... 이후 원문 일부 생략 ...]"

    user_prompt = (
        f"[지원 직무] {target_job or '미지정'}\n"
        f"[지원 회사] {company_name or '미지정'}\n\n"
        f"[자소서 원문]\n{truncated}\n\n"
        f"위 자기소개서를 첨삭하고, {target_job or '해당'} 직무에 맞는 "
        f"예상 면접질문 5개를 생성하며, 개선 포인트를 제시해주세요."
    )

    raw = await call_llm(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.4,
        max_tokens=2000,
        json_mode=True,
    )

    if not raw:
        return _mock_resume_tip(resume_text, target_job, company_name)

    parsed = _parse_llm_json(raw)
    if not parsed:
        # 일시 오류일 수 있으므로 파싱 실패 결과는 캐시하지 않는다.
        logger.warning("LLM 응답 JSON 파싱 실패 (generate_resume_tip, len=%d)", len(raw))
        return {
            "source": "llm",
            "raw_response": raw,
            "edited_resume": "",
            "editing_notes": [],
            "expected_interview_questions": [],
            "improvement_points": [],
            "overall_feedback": raw[:500],
            "kakao_cards": [],
            "privacy_notice": _PRIVACY_NOTICE,
            "message": "LLM 응답을 JSON 으로 파싱하지 못해 원문을 반환합니다.",
        }

    parsed["editing_notes"] = parsed.get("editing_notes") if isinstance(parsed.get("editing_notes"), list) else []
    parsed["expected_interview_questions"] = _list_of_dicts(
        parsed.get("expected_interview_questions"),
        5,
    )
    parsed["improvement_points"] = _list_of_dicts(parsed.get("improvement_points"), 4)
    parsed["source"] = "llm"
    parsed["input"] = {
        "resume_text_length": len(resume_text),
        "target_job": target_job,
        "company_name": company_name,
    }
    parsed["privacy_notice"] = _PRIVACY_NOTICE
    parsed.setdefault("message", "자소서 첨삭 + 면접 예상질문 생성 완료")
    parsed["kakao_cards"] = coaching_cards(parsed)

    # 성공 응답만 캐시 (실패 결과가 TTL 동안 고착되는 것 방지)
    if cache_on:
        cache_set(cache_key, parsed, env_ttl("LLM_CACHE_TTL", 3600))
    return parsed
