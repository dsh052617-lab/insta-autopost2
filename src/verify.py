"""출처 검증: 게시물의 모든 사실이 실제로 가져온 원문에 있는지 코드로 대조한다.

통과 조건 (하나라도 어기면 승인·게시 불가)
1. 출처 구성: 공식 발표(official) 1건 이상, 또는 서로 다른 언론사(press) 2곳 이상
2. 근거 대조: Claude가 적은 근거 구절이 해당 원문에 글자 그대로 있어야 함
3. 숫자 대조: 카드·캡션에 쓴 숫자(두 자리 이상, 또는 %가 붙은 수)가 원문 어딘가에 있어야 함
"""
from __future__ import annotations

import re

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


def _norm(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = text.replace(" ", " ").replace("…", "...")
    return re.sub(r"\s+", " ", text).strip().lower()


def _numbers(text: str) -> set[str]:
    found = set()
    for m in NUM_RE.findall(text):
        raw = m.replace(",", "").replace(" ", "")
        digits = raw.rstrip("%")
        if len(digits.replace(".", "")) >= 2 or raw.endswith("%"):
            found.add(digits)
    return found


def visible_text(post: dict) -> str:
    parts = [post.get("cover_title", ""), post.get("cover_subtitle", ""), post.get("cover_kicker", ""),
             post.get("caption", ""), post.get("question", "")]
    for s in post.get("slides", []):
        parts += [s.get("heading", ""), s.get("highlight", "")] + list(s.get("points", []))
        parts += [f"{t.get('term', '')} {t.get('meaning', '')}" for t in s.get("terms", [])]
    parts += post.get("takeaways", [])
    return "\n".join(parts).replace("**", "")


def source_rule(articles: list[dict]) -> str | None:
    officials = [a for a in articles if a.get("tier") == "official"]
    outlets = {a.get("origin") or a["source"] for a in articles if a.get("tier") != "official"}
    if officials or len(outlets) >= 2:
        return None
    return ("공식 발표가 없고 언론사도 1곳뿐이에요 (공식 발표 1건 이상 또는 언론사 2곳 이상 필요, "
            "같은 통신사 기사를 실은 경우는 1곳으로 셈).")


def check(post: dict, articles: list[dict]) -> dict:
    problems: list[str] = []
    rule = source_rule(articles)
    if rule:
        problems.append(rule)

    corpus = [_norm(a["text"]) for a in articles]
    verified = []
    claims = post.get("claims", [])
    if not claims:
        problems.append("근거(claims)가 하나도 없어요.")
    for c in claims:
        idx = int(c.get("source", 0)) - 1
        ev = _norm(c.get("evidence", ""))
        if not 0 <= idx < len(articles):
            problems.append(f"없는 기사 번호를 근거로 댔어요: \"{c.get('claim', '')}\"")
        elif len(ev) < 8 or ev not in corpus[idx]:
            problems.append(f"근거 구절이 원문에 없어요: \"{c.get('claim', '')}\"")
        else:
            verified.append({"claim": c.get("claim", ""), "source": idx + 1})

    all_numbers = set().union(*(_numbers(a["text"]) for a in articles)) if articles else set()
    for n in sorted(_numbers(visible_text(post)) - all_numbers):
        problems.append(f"원문에서 찾을 수 없는 숫자: {n}")

    return {"passed": not problems, "problems": problems, "verified": verified}
