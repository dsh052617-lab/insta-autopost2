"""Claude 응답이 이상하게 와도 버티는지 시험 (외부 접속 없음).
실행: python tests/robust_mock.py
"""
import copy
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import anthropic  # noqa: E402

import common  # noqa: E402
import verify  # noqa: E402
import writer  # noqa: E402

try:
    import httpx2 as httpx  # anthropic 2.x
except ImportError:  # pragma: no cover
    import httpx

cfg = common.load_config()
good = json.load(open(ROOT / "tests" / "sample_post.json", encoding="utf-8"))


def B(**k):
    return types.SimpleNamespace(**k)


def resp(content, stop="tool_use"):
    return B(stop_reason=stop, content=content, usage=B(input_tokens=1, output_tokens=1))


def tool(name, inp):
    return B(type="tool_use", name=name, input=inp)


class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = B(stream=self.stream)

    def stream(self, **kw):
        self.calls.append(kw)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        outer = self

        class Ctx:
            def __enter__(s):
                return B(get_final_message=lambda: step)

            def __exit__(s, *a):
                return False
        return Ctx()


def bad_request(msg):
    req = httpx.Request("POST", "https://x")
    return anthropic.BadRequestError(msg, response=httpx.Response(400, request=req), body=None)


def use(script):
    writer._FORCED_OK = True
    writer._client = FakeClient(script)
    return writer._client


ok = 0

# 1) 강제 호출 미지원 → 글로만 답함 → 길이 초과 → JSON 문자열로 결과
broken = copy.deepcopy(good)
c = use([bad_request('tool_choice: type "tool" and "any" are not supported for this model.'),
         resp([B(type="text", text="생각해보면...")], "end_turn"),
         resp([tool("card_news", {})], "max_tokens"),
         resp([tool("card_news", json.dumps(broken, ensure_ascii=False))])])
post = writer.write_post(cfg, "economy", [], "a")
assert post["cover_title"] and len(post["slides"]) >= 2 and "tool_choice" not in c.calls[-1]
ok += 1

# 2) 필수 항목이 빠진 결과 → 다시 요청
c = use([resp([tool("card_news", {"cover_title": "제목"})]), resp([tool("card_news", copy.deepcopy(good))])])
post = writer.write_post(cfg, "economy", [], "a")
assert len(c.calls) == 2 and "빠진 항목" in c.calls[1]["messages"][0]["content"]
ok += 1

# 3) 형식이 제각각인 결과 정리 (문자열 숫자, 문자열 목록, '기사 2' 같은 번호)
messy = copy.deepcopy(good)
messy["slides"][0]["points"] = "첫째 요점\n둘째 요점"
messy["slides"][0]["terms"] = [{"term": "기준금리"}]  # 뜻 없음 → 버림
messy["takeaways"] = json.dumps(["하나", "둘"], ensure_ascii=False)
messy["needs_disclaimer"] = "false"
messy["claims"][0]["source"] = "기사 1"
messy["cover_title"] = "첫 줄\\\\n둘째 줄"
p = writer.normalize_post(messy)
assert p["slides"][0]["points"] == ["첫째 요점", "둘째 요점"] and p["slides"][0]["terms"] == []
assert p["takeaways"] == ["하나", "둘"] and p["needs_disclaimer"] is False and p["claims"][0]["source"] == 1
assert "\n" in p["cover_title"]
ok += 1

# 4) 기사 고르기: 번호가 문자열이거나 범위를 벗어남
items = [{"published": "2026-11-14", "source": "연합뉴스", "title": f"기사{i}", "summary": "", "tier": "press"}
         for i in range(5)]
c = use([resp([tool("select_story", {"indices": [99]})]),
         resp([tool("select_story", {"indices": ["3", "1", "3"], "category": "금리·통화"})])])
r = writer.select_story(cfg, "economy", items, [])
assert r["indices"] == [3, 1] and r["angle"] == "" and r["reason"] == ""
ok += 1

# 5) 끝까지 결과를 안 주면 친절한 오류
use([resp([B(type="text", text="음")], "end_turn")] * 5)
try:
    writer.write_post(cfg, "economy", [], "a")
    raise AssertionError("오류가 나야 함")
except RuntimeError as e:
    assert "올바른 결과" in str(e)
ok += 1

# 6) 검증: 이상한 번호도 죽지 않음
res = verify.check({"claims": [{"claim": "x", "source": "몰라", "evidence": "abc"}]}, [{"text": "본문", "source": "a", "tier": "official"}])
assert not res["passed"]
ok += 1

# 7) 웹 검색: 결과 도구 없이 검색만 하고 끝나도 찾은 주소를 돌려줌
use([resp([B(type="web_search_tool_result", content=[B(url="https://www.yna.co.kr/x")])], "end_turn")] * 5)
found = writer.research(cfg, "주제", ["yna.co.kr"])
assert found["urls"] == ["https://www.yna.co.kr/x"]
ok += 1

print(f"robust-ok {ok}/7")
