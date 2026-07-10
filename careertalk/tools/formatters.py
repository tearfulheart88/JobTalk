"""
Kakao 카드 포매터 (기획서 §3.4 Widget 구성)
============================================
도구의 raw 결과(dict)를 카카오톡 채널 메시지에 그대로 렌더링할 수 있는
"카드" 구조로 변환한다. 카카오 Tools 가 커스텀 위젯을 막아두었으므로(기획서 §3.1),
채널 메시지/알림톡 템플릿(basicCard·listCard·카카오 i 오픈빌더)에 1:1 매핑되는
렌더러 중립적 카드 스키마를 사용한다.

카드 스키마:
    {
      "type":  "career" | "job" | "policy" | "coaching",
      "title": str,
      "description": str,                       # 부제(선택)
      "items": [ {"label": str, "value": str} ], # listCard 행
      "tags":  [str],                            # 배지(예: "D-7", "적합도 92")
      "buttons": [ {"label": str, "action": "link"|"message", "value": str} ]
    }

순수 함수 모듈 — 외부 의존성 없음. 표준 라이브러리만 사용.
"""

from __future__ import annotations

import datetime
from typing import Any


# ──────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────
# 마감일은 한국 서비스 기준 — 서버가 UTC 클라우드여도 KST 자정 기준으로 계산 (KST 는 DST 없음)
_KST = datetime.timezone(datetime.timedelta(hours=9), name="KST")


def _today_kst() -> datetime.date:
    return datetime.datetime.now(_KST).date()


def _dday(deadline: str | None) -> str | None:
    """'YYYY-MM-DD'(접두) 마감일 → 'D-7' / 'D-DAY' / '마감' 배지. 파싱 실패 시 None."""
    if not deadline or not isinstance(deadline, str):
        return None
    head = deadline.strip()[:10]
    try:
        end = datetime.date.fromisoformat(head)
    except ValueError:
        return None
    delta = (end - _today_kst()).days
    if delta < 0:
        return "마감"
    if delta == 0:
        return "D-DAY"
    return f"D-{delta}"


def _row(label: str, value: Any) -> dict[str, str] | None:
    """값이 있으면 listCard 행, 없으면 None."""
    if value in (None, "", "None"):
        return None
    return {"label": label, "value": str(value)}


def _compact(rows: list[dict[str, str] | None]) -> list[dict[str, str]]:
    return [r for r in rows if r]


def _stars(score: Any, out_of: int = 5) -> str:
    """0~100 적합도 → 채움/빈 별 문자열."""
    try:
        n = max(0, min(out_of, round(float(score) / (100 / out_of))))
    except (TypeError, ValueError):
        return ""
    return "★" * n + "☆" * (out_of - n)


# ──────────────────────────────────────────────
# 공고 카드 (search_jobs)
# ──────────────────────────────────────────────
def job_cards(jobs: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for j in jobs[:limit]:
        dday = _dday(j.get("deadline"))
        tags = _compact_strs(["데모" if j.get("is_demo") else None, j.get("job_type"), j.get("experience"), dday])
        buttons = []
        if j.get("url"):
            buttons.append({"label": "지원 공고 보기", "action": "link", "value": j["url"]})
        cards.append({
            "type": "job",
            "title": j.get("title", "채용공고"),
            "description": j.get("company_name", ""),
            "items": _compact([
                _row("지역", j.get("location")),
                _row("연봉", j.get("salary")),
                _row("학력", j.get("education")),
            ]),
            "tags": tags,
            "buttons": buttons,
        })
    return cards


# ──────────────────────────────────────────────
# 진로 카드 (analyze_job_fit)
# ──────────────────────────────────────────────
def career_cards(recommended_jobs: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for r in recommended_jobs[:limit]:
        score = r.get("fit_score")
        tags = _compact_strs([
            f"적합도 {score}" if score is not None else None,
            _stars(score) or None,
        ])
        skills = r.get("required_skills") or []
        cards.append({
            "type": "career",
            "title": r.get("job_title", "추천 직무"),
            "description": r.get("reason", ""),
            "items": _compact([
                _row("연봉 밴드", r.get("salary_band")),
                _row("필수 스킬", ", ".join(skills) if isinstance(skills, list) else skills),
                _row("진입 경로", r.get("entry_path")),
                _row("성장 전망", r.get("growth_outlook")),
            ]),
            "tags": tags,
            # 카드에서 바로 해당 직무 공고 검색으로 이어지는 대화형 버튼
            "buttons": [{
                "label": "이 직무 공고 찾기",
                "action": "message",
                "value": f"{r.get('job_title', '')} 신입 공고 찾아줘".strip(),
            }],
        })
    return cards


# ──────────────────────────────────────────────
# 정책 카드 (search_youth_policies)
# ──────────────────────────────────────────────
def policy_cards(policies: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for p in policies[:limit]:
        dday = _dday(p.get("deadline"))
        tags = _compact_strs(["데모" if p.get("is_demo") else None, p.get("category"), p.get("region"), dday])
        buttons = []
        if p.get("application_url"):
            buttons.append({"label": "신청하기", "action": "link", "value": p["application_url"]})
        cards.append({
            "type": "policy",
            "title": p.get("policy_name", "청년정책"),
            "description": p.get("agency", ""),
            "items": _compact([
                _row("지원 금액", p.get("support_amount")),
                _row("신청 자격", p.get("eligibility")),
                _row("신청 기간", p.get("application_period")),
            ]),
            "tags": tags,
            "buttons": buttons,
        })
    return cards


# ──────────────────────────────────────────────
# 코칭 카드 (generate_resume_tip)
# ──────────────────────────────────────────────
def coaching_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    # 1) 첨삭 요약 카드 — 종합 평가 + 개선 포인트
    improvements = result.get("improvement_points") or []
    improve_rows = _compact([
        _row(ip.get("section", "개선"), ip.get("suggestion", ""))
        for ip in improvements[:4]
        if isinstance(ip, dict)
    ])
    cards.append({
        "type": "coaching",
        "title": "자소서 첨삭 결과",
        "description": _truncate(result.get("overall_feedback", ""), 120),
        "items": improve_rows,
        "tags": ["첨삭 완료"],
        "buttons": [],
    })

    # 2) 예상 면접질문 카드 — 질문 리스트
    questions = result.get("expected_interview_questions") or []
    q_rows = _compact([
        _row(f"Q{i}", q.get("question", ""))
        for i, q in enumerate(questions[:5], start=1)
        if isinstance(q, dict)
    ])
    if q_rows:
        cards.append({
            "type": "coaching",
            "title": "예상 면접질문",
            "description": "아래 질문으로 면접을 준비해보세요.",
            "items": q_rows,
            "tags": [f"질문 {len(q_rows)}개"],
            "buttons": [],
        })
    return cards


# ──────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────
def _compact_strs(values: list[Any]) -> list[str]:
    return [str(v) for v in values if v not in (None, "", "None")]


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"
