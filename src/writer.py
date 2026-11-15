"""Claude API로 주제를 고르고 카드뉴스 원고를 쓴다."""
from __future__ import annotations

import json
import os

import anthropic

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY 시크릿이 비어 있어요. Settings → Secrets and variables → Actions에서 등록해 주세요.")
        # 과부하(529)·요청 한도(429)·일시 오류는 SDK가 자동으로 기다렸다 다시 시도
        _client = anthropic.Anthropic(api_key=key, max_retries=6)
    return _client


_FORCED_OK = True  # 모델이 tool_choice 강제 호출을 지원하는지 (Opus 5.5 등은 미지원 → 자동 전환)


def _create(**kwargs):
    """스트리밍으로 요청해 최종 메시지를 받는다 (긴 응답도 시간 제한 없이 안전)."""
    with client().messages.stream(**kwargs) as stream:
        return stream.get_final_message()


def _as_dict(value) -> dict:
    """도구 입력이 dict가 아니라 JSON 문자열로 오는 경우까지 처리."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, dict):
                return loaded
        except ValueError:
            pass
    raise ValueError("도구 입력이 올바른 형식이 아니에요.")


def _call_tool(cfg: dict, system: str, user: str, tool: dict, max_tokens: int = 4000,
               validate=None) -> dict:
    """Claude가 지정한 도구(tool)를 호출하게 해서 구조화된 결과를 받는다.

    - 강제 호출(tool_choice)을 지원하지 않는 모델이면 자동 방식으로 바꾼다.
    - 도구를 부르지 않고 글로만 답하거나, 길이 한도에 걸리거나, 형식이 틀리면 다시 요청한다(최대 5번).
    - validate(result)가 문제 문장을 돌려주면 그 내용을 알려주고 다시 받는다.
    """
    global _FORCED_OK
    messages = [{"role": "user", "content": user}]
    nudge = f"\n\n결과는 반드시 {tool['name']} 도구를 호출해서 제출해. 도구 밖에 결과를 글로 쓰지 마."
    last_error = ""
    for attempt in range(5):
        # 최신 모델은 답하기 전에 생각하는 데도 토큰을 써서 한도를 넉넉히 둔다(요금은 실제 사용량만큼).
        kwargs = dict(model=cfg["claude"]["model"], max_tokens=max(max_tokens, 16000),
                      system=system + nudge, messages=messages, tools=[tool])
        if _FORCED_OK:
            kwargs["tool_choice"] = {"type": "tool", "name": tool["name"]}
        try:
            resp = _create(**kwargs)
        except anthropic.BadRequestError as e:
            if _FORCED_OK and "tool_choice" in str(e):
                print("   (이 모델은 도구 강제 호출을 지원하지 않아 자동 방식으로 전환)")
                _FORCED_OK = False
                continue
            raise
        if resp.stop_reason == "max_tokens":
            last_error = "응답이 길이 한도에 걸려 잘렸어요"
            print("   (응답이 길이 한도에 걸려 다시 요청)")
            continue
        block = next((b for b in resp.content if b.type == "tool_use" and b.name == tool["name"]), None)
        if block is None:
            last_error = "Claude가 결과 도구를 호출하지 않았어요"
            print("   (결과 도구를 부르지 않아 다시 요청)")
            messages = [{"role": "user", "content": user},
                        {"role": "assistant", "content": [b for b in resp.content if b.type == "text"] or "..."},
                        {"role": "user", "content": f"{tool['name']} 도구를 호출해서 결과를 제출해줘."}]
            continue
        try:
            result = _as_dict(block.input)
            problem = validate(result) if validate else None
        except Exception as e:  # 형식이 틀리면 다시 요청
            problem = f"형식 오류: {e}"
        if problem:
            last_error = problem
            print(f"   (결과 형식 문제 → 다시 요청: {problem})")
            messages = [{"role": "user", "content": user + f"\n\n[주의] 직전 결과에 문제가 있었어: {problem}\n"
                                                           "모든 필수 항목을 정해진 형식대로 채워서 다시 제출해."}]
            continue
        print(f"   토큰 사용: 입력 {resp.usage.input_tokens} / 출력 {resp.usage.output_tokens}")
        return result
    raise RuntimeError(f"Claude에게서 올바른 결과를 받지 못했어요({last_error}). 잠시 뒤 다시 실행해 주세요.")


# ── 결과 정리: 빠진 항목·틀린 형식을 바로잡는다 ─────────────

def _str(v, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        return " ".join(_str(x) for x in v)
    return str(v).strip()


def _list(v) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        try:
            loaded = json.loads(v)
            if isinstance(loaded, list):
                return loaded
        except ValueError:
            pass
        return [x for x in (p.strip() for p in v.split("\n")) if x]
    if isinstance(v, dict):
        return [v]
    return list(v)


def _int(v, default: int = -1) -> int:
    try:
        return int(str(v).strip().split()[-1].strip("[]<>#번"))
    except (ValueError, IndexError):
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        return int(digits) if digits else default


def _chart(c) -> dict | None:
    """그래프 카드 데이터: {"title","unit","note","items":[{"label","value"}]} — 항목 2~4개, 값은 숫자."""
    if not isinstance(c, dict):
        return None
    items = []
    for it in _list(c.get("items")):
        if not isinstance(it, dict):
            continue
        raw = _str(it.get("value")).replace(",", "")
        try:
            num = float(raw)
        except ValueError:
            continue
        label = _str(it.get("label"))
        if label and num >= 0:
            items.append({"label": label[:14], "value": raw, "num": num})
    if not 2 <= len(items) <= 4:
        return None
    return {"title": _str(c.get("title"))[:24], "unit": _str(c.get("unit"))[:6],
            "note": _str(c.get("note"))[:40], "items": items}


def normalize_post(post: dict) -> dict:
    """카드 그리기·검증에 필요한 항목을 모두 올바른 형식으로 맞춘다."""
    out = dict(post)
    for k in ("cover_kicker", "cover_title", "cover_subtitle", "question", "caption"):
        out[k] = _str(out.get(k))
    out["cover_title"] = out["cover_title"].replace("\\n", "\n")
    slides = []
    for s in _list(out.get("slides")):
        if isinstance(s, str):
            s = {"heading": s}
        if not isinstance(s, dict):
            continue
        terms = []
        for t in _list(s.get("terms")):
            if isinstance(t, dict) and _str(t.get("term")) and _str(t.get("meaning")):
                terms.append({"term": _str(t["term"]), "meaning": _str(t["meaning"])})
        slide = {"heading": _str(s.get("heading")), "highlight": _str(s.get("highlight")),
                 "points": [_str(p) for p in _list(s.get("points")) if _str(p)][:3],
                 "terms": terms[:2]}
        chart = _chart(s.get("chart"))
        if chart:
            slide["chart"] = chart
            slide["highlight"] = ""          # 그래프 카드는 강조 박스 대신 그래프
            slide["points"] = slide["points"][:1]
        slides.append(slide)
    out["slides"] = [s for s in slides if s["heading"] or s["points"]][:4]
    out["takeaways"] = [_str(t) for t in _list(out.get("takeaways")) if _str(t)][:3]
    out["hashtags"] = [_str(t) for t in _list(out.get("hashtags")) if _str(t)]
    nd = out.get("needs_disclaimer")
    out["needs_disclaimer"] = nd if isinstance(nd, bool) else _str(nd).lower() in ("true", "1", "yes", "예")
    claims = []
    for c in _list(out.get("claims")):
        if isinstance(c, dict):
            claims.append({"claim": _str(c.get("claim")), "source": _int(c.get("source"), 0),
                           "evidence": _str(c.get("evidence"))})
    out["claims"] = claims
    return out


def post_problem(post: dict) -> str | None:
    """정리한 뒤에도 카드로 만들 수 없을 만큼 빠진 게 있으면 그 내용을 돌려준다."""
    p = normalize_post(post)
    missing = [k for k in ("cover_title", "caption") if not p[k]]
    if len(p["slides"]) < 2:
        missing.append("slides(본문 카드 3~4장)")
    if not p["takeaways"]:
        missing.append("takeaways")
    if not p["claims"]:
        missing.append("claims(사실 근거)")
    return f"빠진 항목: {', '.join(missing)}" if missing else None


# ── 1단계: 기사 고르기 ─────────────────────────────────────

CATEGORIES = {
    "ai": ["기술·모델", "산업·기업", "정책·규제", "일자리·교육", "생활·서비스", "안전·윤리", "반도체·인프라"],
    "economy": ["금리·통화", "물가·생활비", "부동산·주거", "금융·투자제도", "고용·소득", "무역·환율",
                "재정·세금", "산업·기업", "글로벌 경제"],
}

SELECT_TOOL = {
    "name": "select_story",
    "description": "카드뉴스로 만들 이야기 하나와 참고할 기사들을 고른다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "고른 이야기의 분야 (아래 목록 중 하나)"},
            "indices": {"type": "array", "items": {"type": "integer"},
                        "description": "같은 이야기를 다룬 기사 번호 1~3개. 가장 정보가 많은 것을 앞에."},
            "angle": {"type": "string", "description": "어떤 관점으로 풀지 한두 문장"},
            "reason": {"type": "string", "description": "왜 이번 주 가장 중요한 이슈인지, 독자에게 어떤 도움이 되는지"},
        },
        "required": ["category", "indices", "angle", "reason"],
    },
}


def select_story(cfg: dict, topic_key: str, items: list[dict], recent_titles: list[str],
                 avoid: list[str] | None = None, recent_categories: list[str] | None = None) -> dict:
    topic = cfg["topics"][topic_key]
    lines = [f"[{i}] ({it['published']}, {it['source']}{', 공식' if it.get('tier') == 'official' else ''}) "
             f"{it['title']} — {it['summary'][:160]}" for i, it in enumerate(items)]
    system = (
        f"너는 인스타그램 정보 계정의 에디터야. 독자는 {cfg['account']['audience']}.\n"
        f"오늘 주제 분야는 '{topic['label']}'이야."
    )
    user = (
        "아래는 최근 7일 동안 나온 기사 목록이야. 이번 주의 이슈 하나를 골라 카드뉴스로 만들 거야.\n"
        "선정 기준 (중요한 순서):\n"
        "① 이번 주 가장 비중 있는 이슈: 여러 매체·기관이 함께 다룬 것, 정책·제도·시장에 실제 변화를 만든 것\n"
        "② 일반 국민(대학생·사회초년생 포함)의 삶과 결정에 실질적으로 도움이 되는 정보: 금리·대출·예금, 물가·생활비, "
        "주거, 세금·지원제도, 투자·금융 제도, 환율·무역, 정부 정책·규제 변화, AI가 산업·경제·생활에 만드는 변화 등\n"
        "③ 분야가 반복되지 않을 것: 아래 '최근 다룬 분야'와 같은 분야는 고르지 말 것. 특히 취업·고용 이야기가 연달아 나오면 안 된다.\n"
        "④ 사실관계가 분명한 것\n"
        "제외: 자극적 사건·갈등 중심 기사, 루머·전망만 있는 기사, 단순 주가 등락 단신, 광고성·인사 기사, 연예성 기사.\n"
        "최후의 선택: 새 AI 도구·제품·모델 출시 소식은 위 기준에 맞는 다른 이슈가 정말 하나도 없을 때만 고른다. "
        "그 경우 reason에 '다른 이슈가 없어 신제품 소식을 골랐다'고 밝혀.\n"
        "가장 최근 기사를 우선해. 같은 비중이면 더 최신 것을 골라.\n"
        "아래 '최근 다룬 주제'(운영자가 직접 올린 '내 주제' 게시물 포함)와 같은 사건·같은 소식은 절대 고르지 말 것. "
        "같은 회사·같은 정책이라도 새로운 사건이면 괜찮아.\n"
        "출처 조건: '공식' 표시 기사 1건 이상을 포함하거나, 서로 다른 언론사 2곳 이상이 같은 사건을 다룬 경우만 고를 수 있어. "
        "indices에는 같은 사건을 다룬 기사만 넣어.\n\n"
        f"분야 목록(category는 이 중 하나): {json.dumps(CATEGORIES[topic_key], ensure_ascii=False)}\n"
        f"최근 다룬 분야(고르지 말 것): {json.dumps(recent_categories or [], ensure_ascii=False)}\n"
        f"최근 다룬 주제: {json.dumps(recent_titles[-10:], ensure_ascii=False)}\n"
        f"이번엔 고르지 말 것(출처 확인 실패): {json.dumps(avoid or [], ensure_ascii=False)}\n\n"
        "기사 목록:\n" + "\n".join(lines)
    )
    def check(r: dict) -> str | None:
        idx = [_int(i) for i in _list(r.get("indices"))]
        return None if any(0 <= i < len(items) for i in idx) else "indices에 목록에 있는 기사 번호를 넣어야 해요"

    result = _call_tool(cfg, system, user, SELECT_TOOL, max_tokens=800, validate=check)
    idx = [_int(i) for i in _list(result.get("indices"))]
    idx = list(dict.fromkeys(i for i in idx if 0 <= i < len(items)))
    result["indices"] = idx[: cfg["news"]["max_articles_per_post"]] or [0]
    result["category"] = _str(result.get("category"))
    result["angle"] = _str(result.get("angle"))
    result["reason"] = _str(result.get("reason"))
    return result


def classify_category(cfg: dict, topic_key: str, title: str, summary: str = "") -> str:
    """내 주제 게시물도 분야(금리·통화 등)를 기록해, 자동 업로드가 같은 분야를 연달아 고르지 않게 한다."""
    options = CATEGORIES.get(topic_key, [])
    tool = {"name": "pick_category", "description": "글의 분야를 하나 고른다.",
            "input_schema": {"type": "object", "properties": {"category": {"type": "string", "enum": options}},
                             "required": ["category"]}}
    cheap = dict(cfg, claude={**cfg["claude"], "model": cfg["claude"].get("research_model") or cfg["claude"]["model"]})
    try:
        r = _call_tool(cheap, "너는 기사 분류 담당이야.", f"제목: {title}\n요약: {summary}\n\n분야를 하나 골라줘.",
                       tool, max_tokens=300)
        cat = _str(r.get("category"))
        return cat if cat in options else ""
    except Exception as e:  # 분류는 부가 기능이라 실패해도 진행
        print(f"   (분야 분류 생략: {e})")
        return ""


# ── 2단계: 카드뉴스 원고 ───────────────────────────────────

POST_TOOL = {
    "name": "card_news",
    "description": "인스타그램 카드뉴스 원고와 사실 근거",
    "input_schema": {
        "type": "object",
        "properties": {
            "cover_kicker": {"type": "string", "description": "표지 위 작은 라벨, 10자 이내. 무엇에 관한 글인지 담담하게 (예: 기준금리 동결)"},
            "cover_title": {"type": "string", "description": "표지 제목. 두 줄, 줄마다 공백 포함 11자 이내, 줄 사이는 \\n. 핵심 사실을 담은 기사 제목처럼"},
            "cover_subtitle": {"type": "string", "description": "표지 부제 28자 이내"},
            "slides": {
                "type": "array", "minItems": 3, "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string", "description": "카드 제목 16자 이내"},
                        "highlight": {"type": "string", "description": "크게 보여줄 핵심 숫자·키워드 10자 이내. 꼭 필요할 때만, 아니면 빈 문자열"},
                        "points": {"type": "array", "minItems": 1, "maxItems": 3,
                                   "items": {"type": "string", "description": "한 줄 요점 32자 이내. 가장 중요한 단어 하나만 **이렇게** 강조"}},
                        "terms": {"type": "array", "maxItems": 2,
                                  "description": "이 카드에 나온 전문용어 풀이 (카드 하단 표시). 일반 독자가 모를 만한 용어만, 없으면 빈 배열",
                                  "items": {"type": "object",
                                            "properties": {"term": {"type": "string", "description": "용어 12자 이내"},
                                                           "meaning": {"type": "string", "description": "쉬운 한 줄 풀이 32자 이내. 숫자·최신 사실 없이 일반적인 뜻만"}},
                                            "required": ["term", "meaning"]}},
                    },
                    "required": ["heading", "highlight", "points", "terms"],
                },
            },
            "takeaways": {"type": "array", "minItems": 2, "maxItems": 3,
                          "items": {"type": "string", "description": "24자 이내 한 줄 요약"}},
            "question": {"type": "string", "description": "캡션 끝에 붙일 질문 한 줄, 40자 이내"},
            "caption": {"type": "string", "description": "인스타 본문 300자 이내. 첫 줄에 핵심 사실 한 문장, 이어서 짧은 문단 1~2개. 이모지·느낌표·해시태그·출처·팔로우 유도 금지"},
            "hashtags": {"type": "array", "items": {"type": "string"}, "maxItems": 8,
                         "description": "# 없이 단어만. 첫 번째는 반드시 AGI시대경제, 나머지는 내용과 직접 관련된 것만"},
            "needs_disclaimer": {"type": "boolean",
                                 "description": "특정 기업·브랜드·종목·코인·금융상품이 언급되거나, 투자·매매 판단으로 오해될 수 있는 내용이면 true. 일반 경제 지표·정책 소식만이면 false"},
            "claims": {
                "type": "array", "minItems": 1,
                "description": "카드·캡션에 쓴 모든 사실(숫자, 날짜, 기관·인물명, 발표 내용, 전망과 그 주체)의 근거. 빠짐없이.",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string", "description": "카드에 쓴 사실을 짧게"},
                        "source": {"type": "integer", "description": "근거 기사 번호 (<기사 N>의 N)"},
                        "evidence": {"type": "string", "description": "그 기사 본문에서 글자 그대로 복사한 연속 구절 15~150자. 고치거나 번역하거나 줄이지 말 것"},
                    },
                    "required": ["claim", "source", "evidence"],
                },
            },
        },
        "required": ["cover_kicker", "cover_title", "cover_subtitle", "slides", "takeaways",
                     "question", "caption", "hashtags", "needs_disclaimer", "claims"],
    },
}

RULES = """[사실과 출처 — 가장 중요]
- 사실(숫자, 날짜, 기관·인물명, 발표 내용)은 아래 제공된 기사 본문에 있는 것만 쓴다. 기억·추측·일반 상식으로 보태지 않는다.
- 숫자는 원문 표기 그대로 쓴다(단위 환산·반올림·'10분의 1' 같은 바꿔 말하기 금지). 원문에 없는 숫자는 쓰지 않는다.
- 카드·캡션의 모든 사실마다 claims에 근거를 단다. evidence는 원문에서 그대로 복사한 구절이어야 하며, 코드가 원문과 글자 단위로 대조한다.
- 전망·의견은 누가 그렇게 말했는지 밝힌다. 계정 의견처럼 단정하지 않는다.
- 기사 문장을 그대로 베끼지 말고 새로 쓴다(evidence 칸만 예외). 특정 종목·코인 매수/매도 권유 금지.

[간결하게 — 가독성]
- 카드에는 설명 문장 대신 짧은 요점만. 요점 하나는 한 줄, 32자 이내. 군더더기(인사말, '알아볼까요', '중요해요' 같은 빈말, 반복) 금지.
- 요점마다 가장 중요한 단어 하나만 **굵게** 표시. 강조를 남발하지 않는다.
- 이모지, 느낌표, 과장어, 클릭 유도 표현 금지. 신뢰할 수 있는 해설 기사처럼 담담하게.
- 영어 기사라도 결과물은 자연스러운 한국어로.
- 전문용어(예: 기준금리, 가계부채, LLM, 파인튜닝)는 요점 안에서 풀어 쓰지 말고, 그 카드의 terms에 한 줄 풀이로 넣는다(카드 하단에 표시됨).
- 독자가 '그래서 나는 뭘 알면/하면 되지?'에 답을 얻도록, 마지막 본문 카드는 독자에게 미치는 영향이나 확인할 점으로 채운다."""


def _articles_block(articles: list[dict]) -> str:
    parts = []
    for i, a in enumerate(articles, 1):
        kind = "공식 발표" if a.get("tier") == "official" else "언론 보도"
        parts.append(f"<기사 {i}>\n출처: {a['source']} ({kind}, {a['published']})\n제목: {a['title']}\n"
                     f"URL: {a['url']}\n본문:\n{a['text']}\n</기사 {i}>")
    return "\n\n".join(parts)


def _system(cfg: dict, topic_key: str) -> str:
    return (f"너는 인스타그램 카드뉴스 '{cfg['account'].get('project', '')}'의 작가야. "
            f"독자는 {cfg['account']['audience']}.\n말투: {cfg['account']['tone']}\n"
            f"분야: {cfg['topics'][topic_key]['label']}\n\n{RULES}")


def write_post(cfg: dict, topic_key: str, articles: list[dict], angle: str) -> dict:
    user = (f"다음 기사들로 카드뉴스를 만들어줘. 풀어갈 관점: {angle}\n"
            "구성: 표지 → 본문 카드 3~4장(무슨 일 → 핵심 내용 → 왜 중요한지) → 한 줄 정리.\n\n"
            + _articles_block(articles))
    return normalize_post(_call_tool(cfg, _system(cfg, topic_key), user, POST_TOOL, max_tokens=8000,
                                     validate=post_problem))


def revise_post(cfg: dict, topic_key: str, post: dict, feedback: str, articles: list[dict]) -> dict:
    post = normalize_post(post)
    current = {k: post[k] for k in POST_TOOL["input_schema"]["required"] if k in post}
    user = ("아래 카드뉴스 초안을 요청대로 고쳐줘. 요청과 관계없는 부분은 유지하고, claims도 고친 내용에 맞게 다시 달아.\n\n"
            f"[요청]\n{feedback}\n\n[현재 초안]\n{json.dumps(current, ensure_ascii=False, indent=2)}\n\n"
            f"[기사]\n{_articles_block(articles)}")
    return normalize_post(_call_tool(cfg, _system(cfg, topic_key), user, POST_TOOL, max_tokens=8000,
                                     validate=post_problem))


INVEST_WORDS = ("주가", "주식", "종목", "증시", "코스피", "코스닥", "나스닥", "시가총액", "상장", "매수", "매도",
                "수익률", "투자자", "펀드", "ETF", "코인", "비트코인", "가상자산", "암호화폐", "목표가", "실적 발표")


def _fix_hashtags(cfg: dict, post: dict) -> None:
    """프로젝트 해시태그를 항상 맨 앞에, 중복 제거, 최대 8개. 투자 안내 문구 필요 여부도 정리."""
    main_tag = cfg["account"].get("project", "").replace(" ", "")
    tags = [t.lstrip("#").replace(" ", "") for t in post.get("hashtags", []) if t.strip("# ")]
    if main_tag:
        tags = [main_tag] + [t for t in tags if t != main_tag]
    post["hashtags"] = list(dict.fromkeys(tags))[:8]
    import verify
    text = verify.visible_text(post)
    post["needs_disclaimer"] = bool(post.get("needs_disclaimer")) or any(w in text for w in INVEST_WORDS)


def write_verified(cfg: dict, topic_key: str, articles: list[dict], angle: str = "",
                   base: dict | None = None, feedback: str = "", retries: int = 2) -> tuple[dict, dict]:
    """원고 작성(또는 수정) → 출처 검증 → 실패 항목을 알려주고 다시 쓰기 (최대 retries회)."""
    import verify
    post = (revise_post(cfg, topic_key, base, feedback, articles) if base
            else write_post(cfg, topic_key, articles, angle))
    _fix_hashtags(cfg, post)
    result = verify.check(post, articles)
    for attempt in range(retries):
        if result["passed"] or verify.source_rule(articles):
            break
        print(f"   검증 실패 {len(result['problems'])}건 → 다시 쓰기 ({attempt + 1}/{retries})")
        fix = ("출처 검증에서 아래 문제가 나왔어. 원문에 없는 내용은 빼거나 원문 표현으로 바꾸고, "
               "evidence는 원문에서 글자 그대로 다시 복사해줘.\n- " + "\n- ".join(result["problems"]))
        post = revise_post(cfg, topic_key, post, fix, articles)
        _fix_hashtags(cfg, post)
        result = verify.check(post, articles)
    return post, result


# ── 내 주제: 신뢰 출처 안에서만 웹 검색 ─────────────────────

PICK_TOOL = {
    "name": "pick_sources",
    "description": "검색 결과 중 카드뉴스에 쓸 출처 페이지를 고른다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4,
                     "description": "주제를 직접 다룬 페이지 URL. 공식 기관 자료를 우선, 그다음 서로 다른 언론사 기사"},
            "category": {"type": "string", "enum": ["ai", "economy"], "description": "AI와 경제 중 더 가까운 분야"},
            "angle": {"type": "string", "description": "독자(일반 국민)에게 도움이 되도록 어떤 관점으로 풀지"},
        },
        "required": ["urls", "category", "angle"],
    },
}


def research(cfg: dict, topic: str, domains: list[str], avoid_urls: list[str] | None = None) -> dict:
    """신뢰 출처 도메인 안에서만 웹 검색해 출처 URL을 고른다."""
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4,
              "allowed_domains": domains},
             PICK_TOOL]
    system = ("너는 인스타그램 정보 계정의 리서처야. 독자는 " + cfg["account"]["audience"] + ".\n"
              "허용된 신뢰 출처(정부·중앙은행·국제기구·기업 공식 발표, 주요 언론)에서만 자료를 찾는다.")
    user = (f"주제: {topic}\n\n"
            "이 주제로 카드뉴스를 만들 자료를 웹 검색으로 찾아줘. 최신 상황이 중요한 주제면 가장 최근 자료를 우선해.\n"
            "공식 발표 1건 이상, 또는 서로 다른 언론사 2곳 이상을 고르는 게 목표야. "
            "찾았으면 pick_sources를 호출해.\n"
            f"쓰지 말 URL: {json.dumps(avoid_urls or [], ensure_ascii=False)}")
    messages = [{"role": "user", "content": user}]
    seen_urls: list[str] = []
    model = cfg["claude"].get("research_model") or cfg["claude"]["model"]
    for _ in range(5):
        try:
            resp = _create(model=model, max_tokens=8000, system=system, messages=messages, tools=tools)
        except anthropic.BadRequestError as e:
            msg = str(e)
            if "web_search" in msg or "web search" in msg.lower():
                raise RuntimeError("Claude 웹 검색을 쓸 수 없어요. Claude Console → Settings → Privacy(또는 "
                                   "Features)에서 Web search를 켜 주세요. 원문: " + msg[:200]) from e
            raise
        pick = None
        for block in resp.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                seen_urls += [r.url for r in block.content if getattr(r, "url", None)]
            if block.type == "tool_use" and block.name == "pick_sources":
                pick = block
        if pick is not None:
            try:
                found = _as_dict(pick.input)
            except ValueError:
                found = {}
            urls = [_str(u) for u in _list(found.get("urls")) if _str(u).startswith("http")]
            if urls:
                return {"urls": urls[:4], "category": _str(found.get("category")) or "economy",
                        "angle": _str(found.get("angle")) or topic}
            break
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":  # 서버 검색이 길어져 잠시 멈춤 → 그대로 이어서
            continue
        messages.append({"role": "user", "content": "이제 pick_sources를 호출해서 고른 URL을 알려줘."})
    return {"urls": list(dict.fromkeys(seen_urls))[:4], "category": "economy", "angle": topic}


def corroborate(cfg: dict, articles: list[dict], domains: list[str]) -> list[str]:
    """출처가 부족할 때: 같은 사건을 다룬 다른 신뢰 출처 기사 URL을 웹 검색으로 찾는다."""
    first = articles[0]
    have = sorted({a.get("origin") or a["source"] for a in articles})
    topic = (f"다음 기사와 '같은 사건'을 보도한 다른 언론사 기사 또는 정부·기관의 공식 발표를 찾아줘.\n"
             f"기사 제목: {first['title']}\n출처: {first['source']} ({first.get('published', '')})\n"
             f"이미 있는 출처(제외): {', '.join(have)}\n"
             "같은 날짜 전후의 같은 사건만. 비슷한 주제의 다른 사건은 안 돼.")
    found = research(cfg, topic, domains, [a["url"] for a in articles])
    return [u for u in found.get("urls", []) if u not in {a["url"] for a in articles}]
