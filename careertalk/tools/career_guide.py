"""First-run guide and FAQ for CareerTalk."""

from __future__ import annotations

from typing import Any, Literal


GuideAction = Literal["start", "examples", "faq", "privacy"]


_FAQ: list[dict[str, Any]] = [
    {
        "id": "start",
        "question": "무엇부터 말하면 되나요?",
        "answer": "지금 가장 막막한 점 하나만 말해 주세요. 목표가 없어도 관심 분야, 가능한 시간, 사는 지역 중 하나면 충분합니다.",
        "keywords": ("시작", "처음", "뭐", "무엇", "입력", "말"),
        "next": "하루 20분으로 취업 준비를 시작하고 싶어요",
    },
    {
        "id": "demo",
        "question": "데모 결과도 실제 공고와 정책인가요?",
        "answer": "아닙니다. Mock 결과에는 데모 표식을 붙입니다. API가 연결되면 출처와 링크가 있는 실시간 결과를 제공하고, 연결 실패 시 데모라고 분명히 알립니다.",
        "keywords": ("데모", "mock", "가짜", "실제", "공고", "정책", "출처"),
        "next": "실시간 공고만 찾아줘",
    },
    {
        "id": "privacy",
        "question": "개인정보와 자기소개서는 어떻게 다루나요?",
        "answer": "주민번호, 상세 주소, 전화번호는 입력하지 마세요. 자기소개서는 첨삭 처리에만 사용하며 서버에 영구 저장하지 않습니다. 라이브 AI 전송 전에는 민감정보를 지우는 것이 안전합니다.",
        "keywords": ("개인정보", "저장", "자소서", "보안", "전화", "주소", "주민"),
        "next": "개인정보 없이 자소서 첨삭하는 법 알려줘",
    },
    {
        "id": "limits",
        "question": "추천이 정답인가요?",
        "answer": "추천은 선택지를 좁히는 참고자료입니다. 지원 자격, 마감일, 급여는 반드시 원문에서 다시 확인하고 최종 결정은 본인이 합니다.",
        "keywords": ("정답", "정확", "믿", "책임", "자격", "마감", "급여"),
        "next": "추천 결과를 검증하는 체크리스트 보여줘",
    },
    {
        "id": "api",
        "question": "API가 없어도 사용할 수 있나요?",
        "answer": "네. 7일 계획과 안내 기능은 API 없이 작동하고, 공고·정책·AI 첨삭은 명확히 표시된 데모 응답으로 안전하게 체험할 수 있습니다.",
        "keywords": ("api", "키", "연결", "오류", "장애", "없이"),
        "next": "API 없이 가능한 기능 보여줘",
    },
]


def _button(label: str, message: str) -> dict[str, str]:
    return {"label": label, "action": "message", "value": message}


def _card(
    title: str,
    description: str,
    *,
    items: list[dict[str, str]] | None = None,
    tags: list[str] | None = None,
    buttons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "guide",
        "title": title,
        "description": description,
        "items": items or [],
        "tags": tags or [],
        "buttons": buttons or [],
    }


def _faq_matches(question: str) -> list[dict[str, Any]]:
    query = question.lower().strip()
    if not query:
        return _FAQ
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in _FAQ:
        score = sum(1 for keyword in item["keywords"] if keyword in query)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:2]] or _FAQ[:3]


async def career_guide(
    action: GuideAction = "start",
    question: str = "",
) -> dict[str, Any]:
    """진로톡의 목적, 첫 사용 예시, 자주 묻는 질문과 개인정보 원칙을 안내합니다."""
    action = str(action or "start").strip().lower()
    question = str(question or "").strip()
    if action not in {"start", "examples", "faq", "privacy"}:
        return {
            "error": "action은 start, examples, faq, privacy 중 하나여야 합니다.",
            "kakao_cards": [],
            "quick_replies": ["처음부터 안내해줘", "사용 예시 보여줘", "자주 묻는 질문"],
        }
    if len(question) > 300:
        return {
            "error": "question은 300자 이하여야 합니다.",
            "kakao_cards": [],
            "quick_replies": ["자주 묻는 질문"],
        }

    if action == "start":
        cards = [
            _card(
                "막막함을 오늘의 행동으로",
                "진로톡은 정답을 대신 고르는 서비스가 아니라, 지금 조건에 맞는 다음 행동을 함께 만드는 청년 진로 멘토입니다.",
                items=[
                    {"label": "1단계", "value": "목표나 고민 한 가지 말하기"},
                    {"label": "2단계", "value": "하루 가능 시간과 장벽 확인하기"},
                    {"label": "3단계", "value": "오늘 20분 행동부터 실행하기"},
                ],
                tags=["첫 사용", "20분 시작", "선택권 존중"],
                buttons=[_button("7일 계획 시작", "하루 20분으로 7일 취업 계획을 만들어줘")],
            ),
            _card(
                "필요한 기능만 바로 선택",
                "목표가 아직 없어도 괜찮습니다. 아래 버튼 하나로 시작할 수 있습니다.",
                items=[
                    {"label": "탐색", "value": "맞는 직무와 진입 경로"},
                    {"label": "기회", "value": "채용공고와 청년정책"},
                    {"label": "준비", "value": "자소서 첨삭과 면접 질문"},
                ],
                tags=["직무", "공고", "정책", "첨삭"],
                buttons=[_button("사용 예시", "진로톡 사용 예시 보여줘"), _button("도움말", "진로톡 자주 묻는 질문")],
            ),
        ]
        message = "반가워요. 지금 가장 막막한 점 하나만 골라 주세요. 길게 설명하지 않아도 됩니다."
        quick_replies = ["7일 계획 시작", "맞는 직무 찾기", "청년정책 찾기", "채용공고 찾기", "도움말"]
    elif action == "examples":
        examples = [
            ("시간이 부족해요", "알바를 병행하며 하루 20분만 가능해요. 7일 계획을 만들어줘"),
            ("경력이 없어요", "경력 없는 비전공자가 데이터 분석가를 준비하는 첫 단계를 알려줘"),
            ("직무를 모르겠어요", "사람을 돕는 일과 글쓰기를 좋아해요. 맞는 직무를 찾아줘"),
            ("지역 기회가 궁금해요", "부산에서 지원할 수 있는 신입 일자리와 청년정책을 찾아줘"),
            ("이직하고 싶어요", "고객응대 2년 경험을 살릴 수 있는 이직 직무를 추천해줘"),
        ]
        cards = [
            _card(
                title,
                prompt,
                tags=["그대로 말해도 돼요"],
                buttons=[_button("이 예시로 시작", prompt)],
            )
            for title, prompt in examples
        ]
        message = "내 상황과 가장 비슷한 예시를 눌러 보세요. 단어 몇 개만 바꿔도 맞춤 안내가 됩니다."
        quick_replies = [prompt for _, prompt in examples[:5]]
    elif action == "privacy":
        cards = [
            _card(
                "안전하게 사용하는 세 가지 원칙",
                "진로 정보는 민감할 수 있어 필요한 정보만 받습니다.",
                items=[
                    {"label": "입력 금지", "value": "주민번호, 계좌번호, 상세 주소, 비밀번호"},
                    {"label": "입력 권장", "value": "관심 분야, 경험, 가능한 시간, 시·도 단위 지역"},
                    {"label": "결과 확인", "value": "공고·정책의 자격과 마감은 원문 재확인"},
                ],
                tags=["최소수집", "영구저장 안 함", "원문 확인"],
                buttons=[_button("FAQ 보기", "진로톡 개인정보 FAQ 보여줘")],
            )
        ]
        message = "민감정보는 빼고도 충분히 도움받을 수 있습니다. 시·도와 경험 정도만 알려 주세요."
        quick_replies = ["안전한 입력 예시", "자소서 개인정보 지우기", "처음으로"]
    else:
        matches = _faq_matches(question)
        cards = [
            _card(
                item["question"],
                item["answer"],
                tags=["자주 묻는 질문"],
                buttons=[_button("이어가기", item["next"])],
            )
            for item in matches
        ]
        message = "궁금한 내용을 확인했어요. 더 구체적으로 물어보면 관련 답만 골라서 안내합니다."
        quick_replies = [item["question"] for item in _FAQ[:5]]

    return {
        "source": "built_in_guide",
        "action": action,
        "message": message,
        "purpose": "청년이 자신의 조건 안에서 실행 가능한 진로 행동을 선택하도록 돕습니다.",
        "mock_mode_independent": True,
        "kakao_cards": cards,
        "quick_replies": quick_replies,
    }
