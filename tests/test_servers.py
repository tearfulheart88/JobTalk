"""
CareerTalk MCP 서버 통합 테스트
================================
4개 도구의 임포트, 호출, Mock 응답 검증.

실행: python tests/test_servers.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# server.py 가 있는 디렉토리를 path 에 추가
_THIS = os.path.dirname(os.path.abspath(__file__))
_SERVER_DIR = os.path.join(_THIS, "..", "careertalk")
_SERVER_DIR = os.path.abspath(_SERVER_DIR)
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

# Windows 콘솔(cp949)에서도 ✓/✗·한글 출력이 깨지지 않도록 UTF-8 로 재설정
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Mock 모드 강제 (테스트는 외부 API 키 없이 실행)
os.environ["MOCK_MODE"] = "true"


PASS = 0
FAIL = 0


def _ok(label: str):
    global PASS
    PASS += 1
    print(f"  ✓ {label}")


def _fail(label: str, err: str):
    global FAIL
    FAIL += 1
    print(f"  ✗ {label} — {err}")


async def test_search_jobs():
    """Tool 1: search_jobs Mock 호출."""
    print("\n[Tool 1] search_jobs")
    from tools.search_jobs import search_jobs

    # 1) 기본 호출
    try:
        result = await search_jobs(keywords="백엔드", count=5)
        assert "jobs" in result, "jobs 키 없음"
        assert len(result["jobs"]) > 0, "공고 0건"
        assert result["source"] == "mock", f"source mismatch: {result.get('source')}"
        job = result["jobs"][0]
        assert "company_name" in job and "title" in job, "job 필드 누락"
        _ok(f"기본 검색: {len(result['jobs'])}건 반환")
    except Exception as e:
        _fail("기본 검색", str(e))
        return

    # 2) 키워드 필터링
    try:
        result = await search_jobs(keywords="React", count=10)
        assert all("React" in j["keyword"] or "React" in j["title"] for j in result["jobs"]), "필터링 실패"
        _ok(f"키워드 필터: '{result['jobs'][0]['title'][:30]}...' 매칭")
    except Exception as e:
        _fail("키워드 필터", str(e))

    # 3) count 제한
    try:
        result = await search_jobs(count=2)
        assert len(result["jobs"]) <= 2, f"count 제한 실패: {len(result['jobs'])}건"
        _ok(f"count 제한: {len(result['jobs'])}건 (요청 2)")
    except Exception as e:
        _fail("count 제한", str(e))


async def test_analyze_job_fit():
    """Tool 2: analyze_job_fit Mock 호출."""
    print("\n[Tool 2] analyze_job_fit")
    from tools.analyze_job_fit import analyze_job_fit

    # 1) IT 관심분야
    try:
        result = await analyze_job_fit(
            interests="IT 개발",
            education="대학교 4년 졸업 예정",
            tendencies="논리적, 분석적, 협업 선호",
            preferred_location="서울",
        )
        assert "recommended_jobs" in result, "recommended_jobs 키 없음"
        assert len(result["recommended_jobs"]) == 5, f"추천 직무 수: {len(result['recommended_jobs'])}"
        assert result["recommended_jobs"][0]["rank"] == 1, "rank 1 없음"
        assert "entry_path" in result["recommended_jobs"][0], "entry_path 없음"
        assert "next_actions" in result, "next_actions 없음"
        _ok(f"IT 진로 분석: TOP1={result['recommended_jobs'][0]['job_title']} (fit={result['recommended_jobs'][0]['fit_score']})")
    except Exception as e:
        _fail("IT 진로 분석", str(e))

    # 2) 비 IT 관심분야
    try:
        result = await analyze_job_fit(interests="마케팅", tendencies="창의적, 소통")
        assert len(result["recommended_jobs"]) == 5, "추천 직무 5개 아님"
        assert "마케팅" in result["recommended_jobs"][0]["job_title"], "마케팅 추천 아님"
        _ok(f"마케팅 진로 분석: TOP1={result['recommended_jobs'][0]['job_title']}")
    except Exception as e:
        _fail("마케팅 진로 분석", str(e))


async def test_search_youth_policies():
    """Tool 3: search_youth_policies Mock 호출."""
    print("\n[Tool 3] search_youth_policies")
    from tools.search_youth_policies import search_youth_policies

    # 1) 기본 호출
    try:
        result = await search_youth_policies(age=24, region="서울", display=10)
        assert "policies" in result, "policies 키 없음"
        assert len(result["policies"]) > 0, "정책 0건"
        assert result["source"] == "mock", f"source mismatch: {result.get('source')}"
        p = result["policies"][0]
        assert "policy_name" in p and "support_amount" in p, "정책 필드 누락"
        assert "application_url" in p, "신청링크 없음"
        _ok(f"정책 검색: {len(result['policies'])}건 반환")
    except Exception as e:
        _fail("정책 검색", str(e))
        return

    # 2) 지역 필터
    try:
        result = await search_youth_policies(region="부산", display=5)
        # '부산' 이 없으면 전국 정책만 반환 (Mock 로직)
        for p in result["policies"]:
            assert p["region"] in ("부산", "전국"), f"지역 필터 실패: {p['region']}"
        _ok(f"지역 필터: {len(result['policies'])}건 (부산/전국)")
    except Exception as e:
        _fail("지역 필터", str(e))

    # 3) display 제한
    try:
        result = await search_youth_policies(display=3)
        assert len(result["policies"]) <= 3, f"display 제한 실패: {len(result['policies'])}건"
        _ok(f"display 제한: {len(result['policies'])}건 (요청 3)")
    except Exception as e:
        _fail("display 제한", str(e))


async def test_generate_resume_tip():
    """Tool 4: generate_resume_tip Mock 호출."""
    print("\n[Tool 4] generate_resume_tip")
    from tools.generate_resume_tip import generate_resume_tip

    # 1) 정상 호출
    try:
        result = await generate_resume_tip(
            resume_text="저는 컴퓨터공학을 전공한 학생입니다. 학창시절 다양한 프로젝트를 진행하며 문제해결능력을 길렀습니다. 귀사에 입사하여 열심히 하겠습니다.",
            target_job="백엔드 개발자",
            company_name="(주)테크스타트",
        )
        assert "edited_resume" in result, "edited_resume 없음"
        assert "expected_interview_questions" in result, "면접질문 없음"
        assert len(result["expected_interview_questions"]) == 5, f"면접질문 5개 아님: {len(result['expected_interview_questions'])}"
        assert "improvement_points" in result, "개선 포인트 없음"
        assert len(result["improvement_points"]) >= 2, "개선 포인트 2개 미만"
        _ok(f"자소서 첨삭: 질문 {len(result['expected_interview_questions'])}개, 개선점 {len(result['improvement_points'])}개")
    except Exception as e:
        _fail("자소서 첨삭", str(e))

    # 2) 빈 입력
    try:
        result = await generate_resume_tip(resume_text="", target_job="개발자")
        assert "error" in result, "빈 입력 에러 없음"
        _ok("빈 입력 처리: error 반환 확인")
    except Exception as e:
        _fail("빈 입력 처리", str(e))


async def test_server_import():
    """server.py 임포트 및 FastMCP 도구 등록 검증."""
    print("\n[Server] server.py 임포트")
    try:
        # server.py 를 모듈로 임포트 (run() 호출 없이)
        import importlib
        spec = importlib.util.spec_from_file_location(
            "careertalk_server", os.path.join(_SERVER_DIR, "server.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # FastMCP 인스턴스 존재
        assert hasattr(mod, "mcp"), "mcp 인스턴스 없음"
        _ok("FastMCP 인스턴스 생성")

        # 도구 등록 확인 — FastMCP 의 tool manager 조회
        # MCP SDK 버전에 따라 내부 API 가 다를 수 있어 try 로 감싼다
        try:
            tools = await mod.mcp.list_tools()
            tool_names = [t.name for t in tools]
            expected = {"search_jobs", "analyze_job_fit", "search_youth_policies", "generate_resume_tip"}
            found = set(tool_names)
            missing = expected - found
            if missing:
                _fail("도구 등록", f"누락: {missing}")
            else:
                _ok(f"4개 Tool 등록 확인: {', '.join(sorted(found))}")
        except Exception as e:
            # list_tools() API 가 다를 수 있음 — _tool_manager 로 폴백
            try:
                tm = getattr(mod.mcp, "_tool_manager", None)
                if tm and hasattr(tm, "_tools"):
                    tool_names = list(tm._tools.keys())
                    expected = {"search_jobs", "analyze_job_fit", "search_youth_policies", "generate_resume_tip"}
                    found = set(tool_names) & expected
                    if len(found) == 4:
                        _ok(f"4개 Tool 등록 확인 (내부 API): {', '.join(sorted(found))}")
                    else:
                        _fail("도구 등록", f"등록된 도구: {tool_names}")
                else:
                    _fail("도구 등록", f"list_tools 실패: {e}")
            except Exception as e2:
                _fail("도구 등록", f"list_tools + fallback 실패: {e2}")

    except Exception as e:
        _fail("server.py 임포트", str(e))


async def test_kakao_cards():
    """카카오 카드 렌더링 (기획서 §3.4 Widget) 검증."""
    print("\n[Cards] kakao_cards 렌더링")
    from tools.search_jobs import search_jobs
    from tools.analyze_job_fit import analyze_job_fit
    from tools.search_youth_policies import search_youth_policies
    from tools.generate_resume_tip import generate_resume_tip

    # 1) 공고 카드 — 링크 버튼 포함
    try:
        r = await search_jobs(keywords="백엔드", count=3)
        cards = r.get("kakao_cards")
        assert isinstance(cards, list) and len(cards) > 0, "공고 카드 없음"
        c = cards[0]
        assert c["type"] == "job" and c["title"], "공고 카드 형식 오류"
        assert any(b["action"] == "link" for b in c["buttons"]), "공고 카드 링크 버튼 없음"
        _ok(f"공고 카드 {len(cards)}장 (바로가기 버튼 포함)")
    except Exception as e:
        _fail("공고 카드", str(e))

    # 2) 진로 카드 — 적합도 태그
    try:
        r = await analyze_job_fit(interests="IT 개발", tendencies="분석적")
        cards = r.get("kakao_cards")
        assert isinstance(cards, list) and len(cards) == 5, f"진로 카드 5장 아님: {len(cards or [])}"
        assert cards[0]["type"] == "career" and cards[0]["tags"], "진로 카드 태그 없음"
        _ok(f"진로 카드 {len(cards)}장 (적합도 태그 포함)")
    except Exception as e:
        _fail("진로 카드", str(e))

    # 3) 정책 카드
    try:
        r = await search_youth_policies(region="서울", display=4)
        cards = r.get("kakao_cards")
        assert isinstance(cards, list) and len(cards) > 0, "정책 카드 없음"
        assert cards[0]["type"] == "policy", "정책 카드 형식 오류"
        _ok(f"정책 카드 {len(cards)}장")
    except Exception as e:
        _fail("정책 카드", str(e))

    # 4) 코칭 카드 — 첨삭 + 면접질문
    try:
        r = await generate_resume_tip(
            resume_text="저는 성실한 신입 지원자입니다. 열심히 하겠습니다.",
            target_job="백엔드 개발자",
        )
        cards = r.get("kakao_cards")
        assert isinstance(cards, list) and len(cards) >= 1, "코칭 카드 없음"
        assert {c["type"] for c in cards} == {"coaching"}, "코칭 카드 타입 오류"
        _ok(f"코칭 카드 {len(cards)}장 (첨삭+면접질문)")
    except Exception as e:
        _fail("코칭 카드", str(e))


def test_response_cache():
    """응답 캐시 TTL 동작 검증 (Mock 모드라 도구 경로는 미적용 — 헬퍼 직접 검증)."""
    print("\n[Cache] 응답 캐시 헬퍼")
    from tools.common import make_cache_key, cache_get, cache_set, cache_clear

    try:
        cache_clear()
        k = make_cache_key("demo", a=1, b="x")
        assert make_cache_key("demo", b="x", a=1) == k, "키가 파라미터 순서에 의존"
        assert cache_get(k) is None, "빈 캐시가 값 반환"
        cache_set(k, {"v": 42}, ttl=60)
        assert cache_get(k) == {"v": 42}, "캐시 저장/조회 실패"
        cache_set(k, {"v": 1}, ttl=0)  # 즉시 만료
        assert cache_get(k) is None, "만료 TTL 미적용"
        _ok("키 안정성 + 저장/조회 + TTL 만료")
    except Exception as e:
        _fail("응답 캐시", str(e))


def test_response_cache_eviction():
    """캐시 최대 개수 초과 시 오래된 항목을 제거하는지 검증."""
    print("\n[Cache] 응답 캐시 크기 제한")
    from tools.common import cache_clear, cache_get, cache_set

    old_limit = os.environ.get("RESPONSE_CACHE_MAX_ENTRIES")
    try:
        os.environ["RESPONSE_CACHE_MAX_ENTRIES"] = "2"
        cache_clear()
        cache_set("k1", {"v": 1}, ttl=60)
        cache_set("k2", {"v": 2}, ttl=60)
        cache_set("k3", {"v": 3}, ttl=60)
        assert cache_get("k1") is None, "가장 오래된 캐시가 제거되지 않음"
        assert cache_get("k2") == {"v": 2}, "유효 캐시 k2 누락"
        assert cache_get("k3") == {"v": 3}, "유효 캐시 k3 누락"
        _ok("최대 2개 유지 + 오래된 항목 제거")
    except Exception as e:
        _fail("응답 캐시 크기 제한", str(e))
    finally:
        cache_clear()
        if old_limit is None:
            os.environ.pop("RESPONSE_CACHE_MAX_ENTRIES", None)
        else:
            os.environ["RESPONSE_CACHE_MAX_ENTRIES"] = old_limit


def test_llm_json_parser():
    """LLM 이 설명문을 섞어도 JSON object 를 추출하는지 검증."""
    print("\n[LLM] JSON 파서 안정성")
    from tools.common import parse_json_object

    try:
        parsed = parse_json_object('아래 결과입니다.\n```json\n{"ok": true, "value": 7}\n```')
        assert parsed == {"ok": True, "value": 7}, f"fenced JSON 파싱 실패: {parsed}"
        parsed = parse_json_object('설명 앞부분 {"answer": "진로톡"} 설명 뒷부분')
        assert parsed == {"answer": "진로톡"}, f"inline JSON 파싱 실패: {parsed}"
        assert parse_json_object("JSON 없음") is None, "잘못된 JSON 이 dict 로 파싱됨"
        _ok("설명문+fence+inline JSON 추출")
    except Exception as e:
        _fail("JSON 파서 안정성", str(e))


def test_external_parser_resilience():
    """외부 API 응답 필드가 문자열/객체로 흔들려도 파싱이 깨지지 않는지 검증."""
    print("\n[Parsers] 외부 응답 파서 방어")
    from tools.search_jobs import _parse_saramin_response
    from tools.search_youth_policies import _strip_internal_fields, get_youth_endpoint

    try:
        jobs = _parse_saramin_response({
            "jobs": {
                "job": {
                    "company": "unexpected",
                    "position": {
                        "title": {"name": "백엔드 개발자"},
                        "location": "서울 > 강남구",
                        "job-type": {"name": "정규직"},
                    },
                    "salary": "면접 후 결정",
                    "expiration-date": "20260731",
                    "url": 123,
                }
            }
        })
        assert len(jobs) == 1, "사람인 단건 응답 파싱 실패"
        assert jobs[0]["title"] == "백엔드 개발자", "title 객체 파싱 실패"
        assert jobs[0]["location"] == "서울 > 강남구", "location 문자열 파싱 실패"
        assert jobs[0]["deadline"] == "2026-07-31", "마감일 정규화 실패"

        policy = _strip_internal_fields({"policy_name": "테스트", "_min_age": "19", "_max_age": "34"})
        assert "_min_age" not in policy and "_max_age" not in policy, "내부 필드 제거 실패"
        os.environ["YOUTH_API_ENDPOINT"] = " https://example.com/custom "
        assert get_youth_endpoint() == "https://example.com/custom", "온통청년 엔드포인트 동적 조회 실패"
        _ok("사람인 파서 + 정책 내부 필드 + 동적 엔드포인트")
    except Exception as e:
        _fail("외부 응답 파서 방어", str(e))
    finally:
        os.environ.pop("YOUTH_API_ENDPOINT", None)


async def test_input_hardening():
    """잘못된 숫자 입력과 외부 API 날짜/필터 보정 검증."""
    print("\n[Hardening] 입력 보정")
    from tools.search_jobs import _normalize_deadline, search_jobs
    from tools.search_youth_policies import _filter_policies, search_youth_policies

    try:
        jobs = await search_jobs(count="bad", start="bad")
        assert jobs["count"] > 0, "잘못된 count/start 입력에서 검색 실패"
        assert _normalize_deadline("20260715") == "2026-07-15", "YYYYMMDD 마감일 정규화 실패"
        assert _normalize_deadline("0") == "1970-01-01", "timestamp 마감일 정규화 실패"
        _ok("채용공고 count/start + 마감일 정규화")
    except Exception as e:
        _fail("채용공고 입력 보정", str(e))

    try:
        policies = await search_youth_policies(display="bad", page_index="bad")
        assert policies["display"] > 0, "잘못된 display/page_index 입력에서 정책 검색 실패"
        filtered = _filter_policies(
            [
                {"policy_name": "서울 청년 교육", "region": "서울", "description": "미취업 교육", "_min_age": "19", "_max_age": "34"},
                {"policy_name": "부산 청년 교육", "region": "부산", "description": "미취업 교육", "_min_age": "19", "_max_age": "34"},
                {"policy_name": "서울 중장년 지원", "region": "서울", "description": "미취업 지원", "_min_age": "40", "_max_age": "64"},
            ],
            age=24,
            region="서울",
            situation="미취업",
        )
        assert len(filtered) == 1 and filtered[0]["policy_name"] == "서울 청년 교육", "정책 후처리 필터 실패"
        _ok("청년정책 display/page_index + 나이/지역/상황 필터")
    except Exception as e:
        _fail("청년정책 입력 보정", str(e))


async def test_required_input_guards():
    """필수 입력이 비었을 때 도구가 예외 대신 명확한 error 를 반환하는지 검증."""
    print("\n[Hardening] 필수 입력 가드")
    from tools.analyze_job_fit import analyze_job_fit
    from tools.generate_resume_tip import generate_resume_tip

    try:
        r = await analyze_job_fit(interests="")
        assert "error" in r and r["recommended_jobs"] == [], "빈 interests 처리 실패"
        r = await generate_resume_tip(resume_text=None, target_job=None, company_name=None)
        assert "error" in r and r["kakao_cards"] == [], "None resume_text 처리 실패"
        _ok("빈 interests + None 자소서 입력 처리")
    except Exception as e:
        _fail("필수 입력 가드", str(e))


async def test_rate_limiter():
    """레이트리미터 — 분당 한도, scope 분리, Mock 모드 비활성."""
    print("\n[Hardening] 레이트리미터")
    from tools import common

    old_mock = os.environ.get("MOCK_MODE")
    try:
        os.environ["MOCK_MODE"] = "false"
        os.environ["RATE_LIMIT_PER_MINUTE"] = "2"
        common.rate_limit_reset()
        assert common.rate_limit_exceeded("external") is None, "1회차가 제한됨"
        assert common.rate_limit_exceeded("external") is None, "2회차가 제한됨"
        msg = common.rate_limit_exceeded("external")
        assert msg is not None and "제한" in msg, "한도 초과가 통과됨"
        assert common.rate_limit_exceeded("llm") is None, "scope 가 분리되지 않음"
        _ok("분당 한도 초과 차단 + scope(llm/external) 분리")

        os.environ["MOCK_MODE"] = "true"
        common.rate_limit_reset()
        for _ in range(5):
            assert common.rate_limit_exceeded("external") is None, "Mock 모드에서 제한됨"
        _ok("Mock 모드에서 자동 비활성")
    except Exception as e:
        _fail("레이트리미터", str(e))
    finally:
        os.environ["MOCK_MODE"] = old_mock or "true"
        os.environ.pop("RATE_LIMIT_PER_MINUTE", None)
        common.rate_limit_reset()


async def test_llm_failure_not_cached():
    """LLM 파싱 실패 응답은 캐시하지 않고, 성공 응답만 캐시한다."""
    print("\n[Cache] LLM 실패 미캐시 / 성공만 캐시")
    import importlib
    # tools/__init__ 이 함수명으로 모듈 속성을 덮으므로 importlib 로 모듈 자체를 가져온다
    ajf = importlib.import_module("tools.analyze_job_fit")
    from tools import common

    old_mock = os.environ.get("MOCK_MODE")
    calls = {"n": 0}

    async def fake_bad_llm(*args, **kwargs):
        calls["n"] += 1
        return "이것은 JSON 이 아닙니다"

    async def fake_good_llm(*args, **kwargs):
        calls["n"] += 1
        return json.dumps({
            "recommended_jobs": [{"rank": 1, "job_title": "테스트직무", "fit_score": 90}],
            "overall_summary": "요약",
            "next_actions": [],
        }, ensure_ascii=False)

    orig_llm = ajf.call_llm
    orig_provider = ajf.get_llm_provider
    orig_rate = ajf.rate_limit_exceeded
    try:
        os.environ["MOCK_MODE"] = "false"
        common.cache_clear()
        ajf.get_llm_provider = lambda: "openai"
        ajf.rate_limit_exceeded = lambda scope: None

        ajf.call_llm = fake_bad_llm
        r1 = await ajf.analyze_job_fit(interests="테스트관심사")
        r2 = await ajf.analyze_job_fit(interests="테스트관심사")
        assert calls["n"] == 2, f"파싱 실패가 캐시됨 (LLM 호출 {calls['n']}회)"
        assert r1["recommended_jobs"] == [] and "raw_response" in r2, "파싱 실패 응답 스키마 오류"
        _ok("파싱 실패 응답은 캐시 안 됨 (재호출 시 LLM 재시도)")

        ajf.call_llm = fake_good_llm
        common.cache_clear()
        calls["n"] = 0
        await ajf.analyze_job_fit(interests="테스트관심사2")
        r4 = await ajf.analyze_job_fit(interests="테스트관심사2")
        assert calls["n"] == 1, f"성공 응답이 캐시되지 않음 (LLM 호출 {calls['n']}회)"
        assert r4["recommended_jobs"][0]["job_title"] == "테스트직무", "캐시된 성공 응답 내용 오류"
        _ok("성공 응답은 캐시됨 (재호출 시 LLM 미호출)")
    except Exception as e:
        _fail("LLM 실패 미캐시", str(e))
    finally:
        ajf.call_llm = orig_llm
        ajf.get_llm_provider = orig_provider
        ajf.rate_limit_exceeded = orig_rate
        os.environ["MOCK_MODE"] = old_mock or "true"
        common.cache_clear()


async def test_dday_kst():
    """D-day 가 KST 기준으로 계산되는지."""
    print("\n[Cards] D-day KST 기준")
    import datetime
    from tools.formatters import _dday, _today_kst

    try:
        today = _today_kst()
        assert _dday(today.isoformat()) == "D-DAY", "오늘(KST)이 D-DAY 가 아님"
        assert _dday((today + datetime.timedelta(days=7)).isoformat()) == "D-7", "D-7 계산 오류"
        assert _dday((today - datetime.timedelta(days=1)).isoformat()) == "마감", "지난 날짜가 마감이 아님"
        _ok("KST 오늘=D-DAY, +7일=D-7, 어제=마감")
    except Exception as e:
        _fail("D-day KST", str(e))


async def test_mock_keyword_tokens():
    """Mock 검색이 다단어 키워드를 토큰 단위로 매칭하는지."""
    print("\n[Mock] 키워드 토큰 매칭")
    from tools.search_jobs import search_jobs

    try:
        r = await search_jobs(keywords="프론트엔드 React", count=5)
        assert r["count"] >= 1, "다단어 키워드가 0건 반환"
        assert "프론트엔드" in r["jobs"][0]["title"], f"1위 결과가 부정확: {r['jobs'][0]['title']}"
        r2 = await search_jobs(keywords="Python", count=5)
        assert r2["count"] >= 2, "단일 토큰 매칭 실패"
        _ok(f"'프론트엔드 React' → {r['count']}건 (1위 정확), 'Python' → {r2['count']}건")
    except Exception as e:
        _fail("키워드 토큰 매칭", str(e))


async def test_policy_pagination():
    """청년정책 다중 페이지 수집 — 필터 통과분이 display 에 찰 때까지 이어서 조회."""
    print("\n[Policies] 다중 페이지 수집")
    import importlib
    syp = importlib.import_module("tools.search_youth_policies")

    try:
        # 페이지당 5건, 서울 정책은 페이지마다 2건만 → display=4 를 채우려면 2페이지 필요
        def _make_page(page: int) -> list[dict]:
            items = []
            for i in range(5):
                seoul = i < 2
                items.append({
                    "policy_id": f"p{page}-{i}",
                    "policy_name": f"정책 {page}-{i}",
                    "region": "서울" if seoul else "부산",
                    "_min_age": "19", "_max_age": "34",
                })
            return items

        calls = {"pages": []}

        async def fake_fetch(page: int):
            calls["pages"].append(page)
            return _make_page(page), 50

        collected, api_total, fetched = await syp._collect_filtered(
            fake_fetch, age=24, region="서울", situation="",
            display=4, page_index=1, max_pages=3,
        )
        assert len(collected) == 4, f"수집 {len(collected)}건 (기대 4)"
        assert fetched == 2 and calls["pages"] == [1, 2], f"페이지 조회 이상: {calls['pages']}"
        assert api_total == 50, "api_total 미전달"
        _ok("필터 후 부족분을 다음 페이지에서 채움 (2페이지, api_total 유지)")

        # 마지막 페이지(요청보다 적게 반환)면 중단
        async def fake_fetch_short(page: int):
            return _make_page(page)[:3], None

        collected2, _, fetched2 = await syp._collect_filtered(
            fake_fetch_short, age=None, region="제주", situation="",
            display=10, page_index=1, max_pages=5,
        )
        assert fetched2 == 1 and collected2 == [], "마지막 페이지에서 중단 안 됨"
        _ok("마지막 페이지 감지 시 조기 중단")

        # 2페이지째 예외 → 부분 결과 유지
        async def fake_fetch_flaky(page: int):
            if page >= 2:
                raise RuntimeError("boom")
            return _make_page(page), None

        collected3, _, fetched3 = await syp._collect_filtered(
            fake_fetch_flaky, age=None, region="서울", situation="",
            display=4, page_index=1, max_pages=3,
        )
        assert fetched3 == 1 and len(collected3) == 2, "부분 결과 유지 실패"
        _ok("후속 페이지 오류 시 부분 결과 반환")
    except Exception as e:
        _fail("다중 페이지 수집", str(e))


async def main():
    print("=" * 60)
    print("CareerTalk MCP 서버 통합 테스트 (Mock 모드)")
    print("=" * 60)

    await test_server_import()
    await test_search_jobs()
    await test_analyze_job_fit()
    await test_search_youth_policies()
    await test_generate_resume_tip()
    await test_kakao_cards()
    test_response_cache()
    test_response_cache_eviction()
    test_llm_json_parser()
    test_external_parser_resilience()
    await test_input_hardening()
    await test_required_input_guards()
    await test_rate_limiter()
    await test_llm_failure_not_cached()
    await test_dday_kst()
    await test_mock_keyword_tokens()
    await test_policy_pagination()

    print("\n" + "=" * 60)
    print(f"결과: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
