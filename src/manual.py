"""직접 만든 원고 등록 — Claude API를 쓰지 않는 '내 주제' 경로.

Claude 대화창에서 만든 원고(JSON)를 이슈 본문에 붙여 넣으면,
  출처 원문 가져오기 → 코드 출처 검증 → 카드 이미지 → 초안 이슈
까지 Claude API 없이(요금 0원) 처리한다. `승인`하면 인스타 API(무료)로 바로 게시.

이슈 제목: `직접: 아무 제목`
이슈 본문: ```json { "topic": "economy", "category": "금리·통화", "request": "...",
                     "sources": ["https://...", ...], "post": { ...카드뉴스 원고... } } ```

  python src/manual.py --issue 12          # Actions에서 자동 실행
  python src/manual.py --file my.json --local
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import news  # noqa: E402
import verify  # noqa: E402
import writer  # noqa: E402  (원고 정리 함수만 사용, Claude 호출 없음)
from common import (DRAFTS, ROOT, git_commit_push, load_config, load_history, now,  # noqa: E402
                    recent_overlap, slot_time)
from draft import SOURCE_KEYS, issue_body, issue_title, render_version  # noqa: E402

JSON_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def parse_body(text: str) -> dict:
    m = JSON_RE.search(text or "")
    raw = m.group(1) if m else (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("본문에서 원고(JSON)를 찾지 못했어요. Claude가 준 ```json … ``` 블록을 통째로 붙여 넣어 주세요.")
    return json.loads(raw[start:end + 1])


def _norm(t: str) -> str:
    return verify._norm(t)


def repair_evidence(post: dict, articles: list[dict], threshold: float = 0.82) -> list[str]:
    """근거 구절이 원문과 글자 단위로 조금 다르면(따옴표·띄어쓰기·요약 도구 차이) 원문에서 가장 비슷한 문장으로 바꾼다.
    비슷한 문장이 없으면 그대로 두어 검증에서 걸리게 한다 (지어낸 근거는 통과 못 함)."""
    notes = []
    for c in post.get("claims", []):
        idx = c.get("source", 0) - 1
        if not 0 <= idx < len(articles):
            continue
        text = articles[idx]["text"]
        ev = c.get("evidence", "")
        if len(_norm(ev)) >= 8 and _norm(ev) in _norm(text):
            continue
        # 원문에서 근거와 길이가 비슷한 구간을 훑으며 가장 비슷한 부분을 찾는다
        nt, ne = _norm(text), _norm(ev)
        best, score = "", 0.0
        if len(ne) >= 8:
            for size in {len(ne), int(len(ne) * 0.9), int(len(ne) * 1.1)}:
                for i in range(0, max(1, len(nt) - size + 1), 2):
                    win = nt[i:i + size]
                    sm = difflib.SequenceMatcher(None, ne, win, autojunk=False)
                    if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                        continue
                    r = sm.ratio()
                    if r > score:
                        best, score = win, r
        if score >= threshold:
            c["evidence"] = best[:300]
            notes.append(f"근거 구절을 원문 문장으로 맞춤 (일치도 {score:.0%}): {c.get('claim', '')}")
    return notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, default=0)
    ap.add_argument("--file", default="")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    cfg = load_config()

    gh = None
    if not args.local:
        import github_api as gh
        gh.ensure_labels()
    body = Path(args.file).read_text(encoding="utf-8") if args.file else (gh.get_issue(args.issue)["body"] or "")

    def fail(msg: str) -> None:
        print("❌ " + msg)
        if gh and args.issue:
            gh.comment(args.issue, "❌ " + msg)
        sys.exit(1)

    try:
        spec = parse_body(body)
    except ValueError as e:
        fail(f"원고를 읽지 못했어요: {e}")
    topic = spec.get("topic", "economy")
    if topic not in cfg["topics"]:
        topic = "economy"
    # scheduled: 매일 예약 작업이 만든 정기 초안 (게시 예정 시각에 올라감). 아니면 '내 주제'(승인 즉시 게시)
    scheduled = spec.get("mode") == "scheduled"
    post_date = spec.get("date") or now(cfg).date().isoformat()
    if scheduled and gh:
        dup = [i for i in gh.open_drafts() if (m := gh.read_marker(i)) and not m.get("custom")
               and m.get("date") == post_date and m.get("topic") == topic and i["number"] != args.issue]
        if dup:
            fail(f"{post_date} {cfg['topics'][topic]['label']} 초안이 이미 있어요(#{dup[0]['number']}). 이 이슈는 닫아 주세요.")
    if gh and args.issue:
        gh.comment(args.issue, "🔎 출처 원문을 가져와 검증하고 카드를 그리는 중이에요 (1~2분, Claude API 요금 없음).")

    print("① 출처 원문 가져오기 (신뢰 출처만)")
    urls = [u for u in spec.get("sources", []) if isinstance(u, str)]
    articles, missing = [], []
    for u in urls:
        a = news.fetch_article(cfg, {"url": u})
        (articles.append(a) if a else missing.append(u))
    if missing:
        fail("아래 출처를 가져오지 못했어요(신뢰 목록 밖이거나 접속 차단·본문 부족). Claude에게 다른 출처로 바꿔 달라고 해 주세요.\n"
             + "\n".join(f"- {u}" for u in missing))
    rule = verify.source_rule(articles)
    if rule:
        fail(rule)

    print("② 원고 정리 + 출처 검증")
    post = writer.normalize_post(spec.get("post", {}))
    problem = writer.post_problem(post)
    if problem:
        fail(f"원고에 {problem}")
    notes = repair_evidence(post, articles)
    writer._fix_hashtags(cfg, post)
    result = verify.check(post, articles)
    print("   " + ("✅ 검증 통과" if result["passed"] else f"❌ 검증 실패: {result['problems']}"))

    # 자동 업로드와 같은 기사인지 확인
    others = load_history()
    if gh:
        try:
            others += [p for p in gh.pending_posts(ROOT) if p.get("number") != args.issue]
        except Exception as e:
            print(f"   (대기 중 초안 확인 실패: {e})")
    overlaps = recent_overlap(cfg, post.get("cover_title", ""), [a["url"] for a in articles], others)
    followup = spec.get("followup") if isinstance(spec.get("followup"), dict) else None
    if overlaps and followup:
        # 후속 보도: 이전 글 이후에 나온 새 기사가 있어야만 허용 (같은 내용 반복 금지)
        last = max((o.get("date") or "") for o in overlaps)
        newer = [a for a in articles if (a.get("published") or "") > last]
        if newer and str(followup.get("new", "")).strip():
            print(f"   후속 보도로 허용: 이전 글({last}) 이후 기사 {len(newer)}건")
            overlaps = []
        else:
            fail("후속 보도로 올리려면 이전 글 이후에 나온 새 기사와, 새로 추가된 내용(followup.new)이 필요해요.\n"
                 + "\n".join(f"- {o.get('date', '')} {o.get('title', '')}" for o in overlaps[:3]))
    if overlaps and scheduled:  # 자동 초안은 예전 글과 겹치면 절대 등록하지 않는다 (기간 제한 없음)
        fail("이미 게시했거나 게시 예정인 글과 내용이 겹쳐서 등록하지 않았어요.\n"
             + "\n".join(f"- {o.get('date', '')} {o.get('title', '')} ({o['why']})" for o in overlaps[:3])
             + "\n새로 추가된 내용이 있는 후속 보도라면 followup을 넣어 다시 만들고, 아니면 다른 이슈로 만들어 주세요.")

    stamp = now(cfg).strftime("%Y%m%d-%H%M")
    name = f"{post_date}-{topic}" if scheduled else f"manual-{stamp}"
    draft_dir = (ROOT / "preview" / name) if args.local else (DRAFTS / name)
    if scheduled and not args.local and (draft_dir / "post.json").exists():
        draft_dir = DRAFTS / f"{post_date}-{topic}-{stamp[-4:]}"  # 예전에 취소된 같은 날짜 초안과 겹치지 않게
    draft_dir.mkdir(parents=True, exist_ok=True)
    category = spec.get("category", "")
    kind = spec.get("kind") if spec.get("kind") in ("news", "term", "history", "compare") else "news"
    data = {"date": post_date, "topic": topic, "version": 1, "post": post, "kind": kind,
            "custom": not scheduled,
            "request": spec.get("request", "") or post.get("cover_title", "").replace("\n", " "),
            "sources": [{k: a[k] for k in SOURCE_KEYS} for a in articles],
            "story": {"reason": spec.get("reason") or ("Claude 예약 작업이 고른 오늘의 이슈 (API 미사용)" if scheduled
                                                       else "운영자가 Claude 대화창에서 직접 만든 원고 (API 미사용)"),
                      "angle": spec.get("angle") or spec.get("request", ""),
                      "category": category if category in writer.CATEGORIES.get(topic, []) else ""},
            "verification": result}

    print("③ 이미지 만들기")
    paths = render_version(cfg, data, draft_dir)
    (draft_dir / "post.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.local:
        print(f"✅ 미리보기 완료: {draft_dir}")
        for n in notes:
            print("   " + n)
        return

    git_commit_push(f"manual draft: {stamp}", [draft_dir])
    gh.update_issue(args.issue, title=issue_title(cfg, data), body=issue_body(cfg, data, paths, draft_dir))
    gh.add_labels(args.issue, ["draft"])
    when = f"{post_date} {slot_time(cfg, topic)}"
    ok_msg = (f"🆕 초안을 본문에 올렸어요. 확인하고 `승인`하면 {when}에 게시돼요." if scheduled
              else "🆕 초안을 본문에 올렸어요. 확인하고 `승인`하면 바로 게시돼요.")
    msg = (ok_msg if result["passed"]
           else "⚠️ 출처 검증을 통과하지 못했어요. 본문의 문제 목록을 Claude에게 보여주고 고친 원고로 새 이슈를 만들어 주세요.")
    if notes:
        msg += "\n\n" + "\n".join(f"- {n}" for n in notes)
    if overlaps:
        msg += ("\n\n⚠️ 예전 글과 내용이 겹쳐요. 새로 추가된 내용이 없으면 올리지 말고 `취소`해 주세요.\n" + "\n".join(
            f"- {o.get('date', '')} {o.get('title', '')} ({o['why']})" for o in overlaps[:3]))
    gh.comment(args.issue, msg)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import github_api as gh_api
        num = next((int(a.split("=", 1)[1] or 0) for a in sys.argv if a.startswith("--issue=")), 0)
        gh_api.report_error(e, "직접 만든 원고 등록", num)
        raise
