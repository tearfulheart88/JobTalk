"""CareerTalk's deterministic, barrier-aware action-plan tool."""

from __future__ import annotations

import hashlib
from typing import Any


_ROLE_KITS = (
    {
        "keywords": ("개발", "백엔드", "프론트", "python", "java", "코딩", "it"),
        "role": "개발 직무",
        "artifact": "작게 동작하는 기능 1개와 README",
        "practice": "핵심 개념 1개를 익히고 코드로 재현",
    },
    {
        "keywords": ("데이터", "분석", "sql", "ai", "인공지능"),
        "role": "데이터 직무",
        "artifact": "질문-분석-결론이 보이는 미니 분석 노트",
        "practice": "작은 데이터셋으로 지표 1개를 계산하고 해석",
    },
    {
        "keywords": ("디자인", "ux", "ui", "콘텐츠"),
        "role": "디자인·콘텐츠 직무",
        "artifact": "문제와 개선 이유가 담긴 전후 비교 시안",
        "practice": "좋은 사례 2개를 관찰하고 선택 이유를 한 문장으로 정리",
    },
    {
        "keywords": ("마케팅", "브랜드", "광고", "기획"),
        "role": "마케팅·기획 직무",
        "artifact": "타깃-메시지-성과지표가 있는 1페이지 제안",
        "practice": "관심 서비스 1개의 고객과 핵심 메시지를 분석",
    },
)


def _role_kit(goal: str) -> dict[str, Any]:
    lowered = goal.lower()
    for kit in _ROLE_KITS:
        if any(keyword in lowered for keyword in kit["keywords"]):
            return kit
    return {
        "keywords": (),
        "role": "관심 직무",
        "artifact": "문제-행동-결과가 보이는 작은 포트폴리오 1개",
        "practice": "관심 직무 공고 3개에서 반복되는 역량을 찾아 연습",
    }


def _barrier_strategy(barrier: str, minutes: int) -> dict[str, Any]:
    lowered = barrier.lower()
    rules = (
        {
            "label": "시간 부족",
            "keywords": ("시간", "바빠", "알바", "육아", "병행"),
            "strategy": f"하루 {minutes}분 안에 끝나는 한 가지 행동만 배치합니다.",
            "fallback": "시간이 없는 날은 10분 축소판으로 바꾸고 연속성을 지키세요.",
        },
        {
            "label": "경험 부족",
            "keywords": ("경력", "경험", "포트폴리오", "신입"),
            "strategy": "작은 결과물을 만들고 문제-행동-결과 순서로 증거를 남깁니다.",
            "fallback": "실무 경험 대신 개인·수업·봉사 프로젝트에서 본인이 바꾼 점을 찾으세요.",
        },
        {
            "label": "비용 부담",
            "keywords": ("돈", "비용", "경제", "교육비"),
            "strategy": "무료 자료와 청년정책을 우선 연결하고 유료 결제를 계획에서 제외합니다.",
            "fallback": "학습 결제 전에 진로톡에서 받을 수 있는 교육·구직 정책을 먼저 검색하세요.",
        },
        {
            "label": "지역 제약",
            "keywords": ("지역", "지방", "원격", "거리", "이사"),
            "strategy": "거주 지역·원격 조건을 먼저 고정하고 이동 가능한 범위를 넓히지 않습니다.",
            "fallback": "지역 공고가 적으면 원격·하이브리드와 지역 청년센터 지원을 함께 확인하세요.",
        },
        {
            "label": "시작 장벽",
            "keywords": ("불안", "막막", "자신", "두려", "실패"),
            "strategy": f"완성 대신 {min(minutes, 15)}분 시작을 성공 기준으로 삼습니다.",
            "fallback": "막히면 파일을 열고 첫 문장 또는 첫 줄만 작성해도 완료로 기록하세요.",
        },
    )
    matched = [rule for rule in rules if any(word in lowered for word in rule["keywords"])]
    if matched:
        # 구체적인 생활 제약을 먼저 다루고 카드가 길어지지 않도록 최대 두 개를 결합한다.
        selected = matched[:2]
        return {
            "label": " · ".join(str(rule["label"]) for rule in selected),
            "detected": [str(rule["label"]) for rule in matched],
            "strategy": " ".join(str(rule["strategy"]) for rule in selected),
            "fallback": " ".join(str(rule["fallback"]) for rule in selected),
        }
    return {
        "label": "실행 장벽",
        "detected": ["실행 장벽"],
        "strategy": "가장 작은 행동부터 완료해 다음 선택에 필요한 증거를 만듭니다.",
        "fallback": "막힌 이유를 한 문장으로 적고 다음 행동을 절반 크기로 줄이세요.",
    }


def _missions(
    goal: str,
    current_skills: str,
    kit: dict[str, Any],
    barrier: dict[str, Any],
    minutes: int,
) -> list[dict[str, Any]]:
    skill_text = current_skills or "지금 할 수 있는 것"
    templates = [
        (
            "목표를 한 문장으로 고정",
            f"'{goal}' 목표와 지원하고 싶은 이유를 각각 한 문장으로 적기",
            "목표 1문장과 이유 1문장이 남아 있음",
        ),
        (
            "내 증거 찾기",
            f"{skill_text}에서 {kit['role']}에 연결할 수 있는 경험 2개 찾기",
            "경험마다 내가 한 행동을 동사로 1개씩 적음",
        ),
        (
            "필수 역량 하나만 연습",
            str(kit["practice"]),
            "배운 점 3줄과 막힌 점 1줄이 남아 있음",
        ),
        (
            "작은 결과물 만들기",
            str(kit["artifact"]),
            "다른 사람이 열어볼 수 있는 초안 링크 또는 파일이 있음",
        ),
        (
            "공고를 평가표로 비교",
            f"{kit['role']} 공고 3개에서 공통 역량·지역·마감일을 표로 정리",
            "지원·보류·제외 중 하나를 공고마다 결정함",
        ),
        (
            "경험을 자소서 문장으로 변환",
            "가장 좋은 경험 1개를 상황-행동-결과 3문장으로 작성",
            "숫자 또는 전후 변화가 포함된 3문장이 있음",
        ),
        (
            "한 건 지원하고 회고",
            "가장 적합한 공고 1건에 지원하거나 지원에 필요한 마지막 빈칸을 채우기",
            "지원 완료 또는 다음 지원을 막는 조건 1개가 명확함",
        ),
    ]
    missions = []
    for index, (title, task, done) in enumerate(templates, start=1):
        missions.append(
            {
                "day": index,
                "title": title,
                "minutes": minutes,
                "task": task,
                "done_definition": done,
                "if_stuck": barrier["fallback"],
            }
        )
    return missions


def _cards(
    missions: list[dict[str, Any]],
    barrier: dict[str, Any],
    goal: str,
) -> list[dict[str, Any]]:
    today = missions[0]
    return [
        {
            "type": "mission",
            "title": f"오늘의 {today['minutes']}분 미션",
            "description": today["title"],
            "tags": ["오늘 시작", barrier["label"]],
            "items": [
                {"label": "할 일", "value": today["task"]},
                {"label": "완료 기준", "value": today["done_definition"]},
                {"label": "막히면", "value": today["if_stuck"]},
            ],
            "buttons": [
                {"label": "1일차 시작", "action": "message", "value": "1일차 미션을 시작할게"},
            ],
        },
        {
            "type": "roadmap",
            "title": "7일 커리어 브리지",
            "description": f"{goal} 목표를 정보 탐색에서 실제 지원까지 연결합니다.",
            "tags": ["7일 계획", "저비용", "작은 행동"],
            "items": [
                {"label": f"Day {item['day']}", "value": item["title"]}
                for item in missions
            ],
            "buttons": [
                {"label": "맞춤 공고 찾기", "action": "message", "value": f"{goal} 관련 공고 찾아줘"},
                {"label": "지원정책 찾기", "action": "message", "value": "내가 받을 수 있는 청년 취업정책 찾아줘"},
            ],
        },
    ]


async def build_career_action_plan(
    goal: str,
    current_skills: str = "",
    barrier: str = "막막함",
    available_minutes_per_day: int = 30,
) -> dict[str, Any]:
    """Turn a career goal and practical barrier into a seven-day micro-action plan."""
    goal = str(goal or "").strip()
    current_skills = str(current_skills or "").strip()
    barrier = str(barrier or "").strip() or "막막함"
    if not goal:
        return {"error": "goal이 비어있습니다. 이루고 싶은 진로·취업 목표를 알려주세요.", "missions": [], "kakao_cards": []}
    if len(goal) > 300 or len(current_skills) > 500 or len(barrier) > 300:
        return {"error": "goal·barrier는 300자, current_skills는 500자 이하여야 합니다.", "missions": [], "kakao_cards": []}
    if isinstance(available_minutes_per_day, bool):
        return {"error": "available_minutes_per_day는 10~180 사이의 숫자여야 합니다.", "missions": [], "kakao_cards": []}
    try:
        minutes = int(available_minutes_per_day)
    except (TypeError, ValueError):
        return {"error": "available_minutes_per_day는 10~180 사이의 숫자여야 합니다.", "missions": [], "kakao_cards": []}
    if not 10 <= minutes <= 180:
        return {"error": "available_minutes_per_day는 10~180 사이여야 합니다.", "missions": [], "kakao_cards": []}

    kit = _role_kit(goal)
    barrier_plan = _barrier_strategy(barrier, minutes)
    missions = _missions(goal, current_skills, kit, barrier_plan, minutes)
    plan_seed = "|".join((goal, current_skills, barrier, str(minutes)))
    plan_id = "career-" + hashlib.sha256(plan_seed.encode("utf-8")).hexdigest()[:10]
    return {
        "source": "deterministic_plan",
        "plan_id": plan_id,
        "message": f"'{goal}' 목표를 오늘 시작할 수 있는 {minutes}분 행동과 7일 계획으로 바꿨어요.",
        "goal": goal,
        "focus_role": kit["role"],
        "barrier_support": barrier_plan,
        "today_mission": missions[0],
        "missions": missions,
        "one_tap_prompts": [
            f"내 관심 분야와 성향을 바탕으로 {kit['role']} 적합도를 분석해줘",
            f"{goal} 관련 신입 공고를 찾아줘",
            "내가 받을 수 있는 청년 취업·교육 정책을 찾아줘",
            f"{goal} 지원용 자기소개서를 첨삭해줘",
        ],
        "kakao_cards": _cards(missions, barrier_plan, goal),
        "privacy_notice": "계획 생성에는 이름·전화번호·주민번호가 필요하지 않으며 입력은 외부 API로 전송되지 않습니다.",
        "limitations": "추천은 합격을 보장하지 않습니다. 실제 공고 자격·마감과 정책 신청 조건은 원문에서 다시 확인하세요.",
    }
