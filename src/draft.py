"""초안 만들기: 신뢰 출처 수집 → Claude가 고르고 작성 → 출처 검증 → 카드 이미지 → GitHub 이슈로 검토 요청.

사용법
  python src/draft.py                 # 다음 게시 일정에 맞춰 자동
  python src/draft.py --topic economy # 주제 지정
  python src/draft.py --local         # GitHub 없이 내 컴퓨터에서 미리보기만 (ANTHROPIC_API_KEY 필요)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import news  # noqa: E402
import render  # noqa: E402
import verify  # noqa: E402
import writer  # noqa: E402
from common import (DRAFTS, ROOT, date_label, git_commit_push, load_config,  # noqa: E402
                    load_history, next_post_slot, raw_url, recent_overlap, slot_time)

SOURCE_KEYS = ("title", "url", "source", "published", "tier")


# ── 공용 ─────────────────────────────────────────────────

def build_caption(post: dict, sources: list[dict]) -> str:
    src_lines = "\n".join(f"- {s['source']}" + (f" ({str(s['published'])[:10]})" if s.get("published") else "")
                          for s in sources)
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in post["hashtags"][:8])
    disclaimer = ("※ 특정 기업·상품에 대한 투자 권유가 아닌 정보 제공 목적의 글이에요. "
                  "투자 판단은 본인의 책임이에요.\n") if post.get("needs_disclaimer") else ""
    caption = (f"{post['caption'].strip()}\n\n{post['question']}\n\n"
               f"출처\n{src_lines}\n\n{disclaimer}"
               f"이 글은 AI의 도움을 받아 작성하고, 출처 원문과 대조한 뒤 운영자가 검토했어요.\n\n{tags}")
    return caption[:2200]


def fetch_articles(cfg: dict, sources: list[dict]) -> list[dict]:
    got = [news.fetch_article(cfg, s) for s in sources]
    return [a for a in got if a]


def render_version(cfg: dict, data: dict, draft_dir: Path) -> list[Path]:
    date = dt.date.fromisoformat(data["date"])
    return render.render_all(data["post"], cfg, data["topic"], draft_dir / f"v{data['version']}",
                             date.strftime("%Y.%m.%d"), data["sources"],
                             kind=data.get("kind", "news"))


def issue_title(cfg: dict, data: dict) -> str:
    date = dt.date.fromisoformat(data["date"])
    label = cfg["topics"][data["topic"]]["label"]
    title = data["post"]["cover_title"].replace("\\n", " ").replace("\n", " ")
    mark = "" if data["verification"]["passed"] else "❌ 출처 검증 실패 · "
    when = "내 주제" if data.get("custom") else date_label(date)
    return f"[{when} {label}] {mark}{title}"


def verification_md(data: dict) -> str:
    v = data["verification"]
    srcs = data["sources"]
    if v["passed"]:
        rows = "\n".join(
            f"| {c['claim']} | [{srcs[c['source'] - 1]['source']}]({srcs[c['source'] - 1]['url']}) |"
            for c in v["verified"] if c["source"] - 1 < len(srcs))
        return (f"### ✅ 출처 검증 통과\n사실 {len(v['verified'])}건의 근거 구절을 원문과 글자 단위로 대조했고, "
                f"카드의 숫자도 모두 원문에서 확인했어요.\n\n| 카드에 쓴 사실 | 근거 원문 |\n|---|---|\n{rows}")
    probs = "\n".join(f"- {p}" for p in v["problems"])
    return ("### ❌ 출처 검증 실패 — 이 상태로는 승인·게시할 수 없어요\n"
            f"{probs}\n\n`수정: 원문에 없는 내용은 빼줘`처럼 고치거나 `취소`해 주세요.")


def issue_body(cfg: dict, data: dict, image_paths: list[Path], draft_dir: Path) -> str:
    from github_api import make_marker
    date = dt.date.fromisoformat(data["date"])
    label = cfg["topics"][data["topic"]]["label"]
    imgs = " ".join(f'<img src="{raw_url(p)}" width="260">' for p in image_paths)
    srcs = "\n".join(
        f"- {'🏛 공식 발표' if s.get('tier') == 'official' else '📰 언론 보도'} · "
        f"[{s['title']}]({s['url']}) — {s['source']}, {s['published']}" for s in data["sources"])
    marker = make_marker({"dir": draft_dir.relative_to(ROOT).as_posix(), "date": data["date"],
                          "topic": data["topic"], "version": data["version"],
                          "custom": bool(data.get("custom"))})
    if data.get("custom"):
        head = f"## ✍️ 내 주제 카드뉴스 · {label}\n요청 주제: {data.get('request', '')}"
        approve = "> - `승인` → 바로 인스타에 올라가요 (출처 검증을 통과한 초안만 가능)"
    else:
        head = f"## 📮 {date_label(date)} {slot_time(cfg, data['topic'])} 게시 예정 · {label}"
        approve = "> - `승인` → 예정 시각에 인스타에 올라가요 (출처 검증을 통과한 초안만 가능)"
    return f"""{head}

> **초안을 확인하고 댓글로 알려주세요.** 승인하지 않으면 게시되지 않아요.
{approve}
> - `수정: 고칠 내용` → 새 버전을 만들어 다시 검증한 뒤 여기에 올려요
> - `지금 게시` → 바로 올려요
> - `취소` → 이번 회차는 건너뛰어요

### 카드 미리보기 (v{data['version']})
{imgs}

{verification_md(data)}

### 참고 기사
{srcs}

### 캡션
```text
{build_caption(data['post'], data['sources'])}
```

<details><summary>이 기사를 고른 이유</summary>

{data['story'].get('reason', '')}

관점: {data['story'].get('angle', '')}
</details>

{marker}
"""


def _repeats(category: str, recent: list[str]) -> bool:
    """'고용·소득'과 '일자리·교육'처럼 AI·경제에 걸친 같은 계열도 반복으로 본다."""
    if not category:
        return False
    jobs = {"고용·소득", "일자리·교육"}
    return category in recent or (category in jobs and bool(jobs & set(recent)))


# ── 메인 ──────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="")
    ap.add_argument("--date", default="", help="게시 예정일 YYYY-MM-DD")
    ap.add_argument("--force", action="store_true", help="같은 날짜 초안이 있어도 새로 만들기")
    ap.add_argument("--local", action="store_true", help="GitHub 이슈 없이 미리보기만")
    args = ap.parse_args()

    cfg = load_config()
    if args.topic and args.topic not in cfg["topics"]:
        sys.exit(f"알 수 없는 주제: {args.topic} (config.yaml의 topics 확인)")
    date, topic = next_post_slot(cfg, args.topic or None)
    if args.date:
        date = dt.date.fromisoformat(args.date)
    if topic not in cfg["topics"]:
        sys.exit(f"알 수 없는 주제: {topic} (config.yaml의 topics 확인)")
    print(f"▶ 게시 예정: {date} / 주제: {topic}")
    skip_file = ROOT / "data" / "skip" / f"{date.isoformat()}-{topic}.txt"
    if skip_file.exists() and not args.force:  # 아침 예약 작업이 '오늘은 올리지 않음'으로 정한 날 → 예비 초안도 만들지 않음
        print(f"오늘은 건너뛰기로 정한 날이에요: {skip_file.read_text(encoding='utf-8').strip()[:200]}")
        return

    same_day: list[dict] = []
    if not args.local:
        import github_api as gh
        gh.ensure_labels()
        def _early_published(i: dict) -> bool:
            # 예정일보다 먼저 '지금 게시'로 올라간 초안은 그날 자리를 막지 않는다
            labels = {lb.get("name") for lb in i.get("labels", [])}
            closed = (i.get("closed_at") or "")
            if "published" not in labels or not closed:
                return False
            kst = (dt.datetime.fromisoformat(closed.replace("Z", "+00:00")) + dt.timedelta(hours=9)).date()
            return kst < date

        same_day = [i for i in gh.recent_drafts()
                    if (m := gh.read_marker(i)) and not m.get("custom") and m.get("date") == date.isoformat()
                    and m.get("topic") == topic and not _early_published(i)]
        if same_day and not args.force:
            print(f"이 날짜 초안이 이미 있어요(열림·게시·취소 포함): #{same_day[0]['number']} — 건너뜀 "
                  "(새로 만들려면 Run workflow에서 force 체크)")
            return
        same_day = [i for i in same_day if i["state"] == "open"]

    history = load_history()
    # 아직 게시 전인 다른 초안(특히 '내 주제')도 이미 다룬 것으로 보고 피한다
    pending = []
    if not args.local:
        try:
            pending = [p for p in gh.pending_posts(ROOT)
                       if p["custom"] or p["date"] != date.isoformat() or p["topic"] != topic]
        except Exception as e:
            print(f"   (대기 중 초안 확인 실패: {e})")
    history = history + pending
    used_urls = {u for h in history for u in h.get("urls", [])}
    # AI·경제를 가리지 않고 최근 다룬 주제 전체를 알려줘 겹치지 않게
    recent_titles = [h["title"] for h in history if h.get("title")][-12:]
    # 분야 반복 방지: 같은 주제의 최근 2개 + 전체 최근 2개(취업·고용 같은 이야기가 AI·경제에 걸쳐 반복되는 것 방지)
    recent_categories = list(dict.fromkeys(
        [h.get("category", "") for h in history if h.get("topic") == topic][-2:]
        + [h.get("category", "") for h in history][-2:]))
    recent_categories = [c for c in recent_categories if c]

    print("① 신뢰 출처에서 최근 7일 기사 수집")
    items = news.collect(cfg, cfg["topics"][topic]["feeds"], cfg["news"]["lookback_days"], used_urls)
    if len(items) < 2:
        sys.exit("신뢰 출처에서 최근 기사를 충분히 찾지 못했어요. 피드 주소나 lookback_days를 확인해주세요.")

    print(f"② 기사 고르기 + 원문 확보 (후보 {len(items)}건)")
    avoid: list[str] = []
    story, articles = None, []
    for attempt in range(4):
        story = writer.select_story(cfg, topic, items, recent_titles, avoid, recent_categories)
        chosen = [items[i] for i in story["indices"]]
        if _repeats(story.get("category", ""), recent_categories):
            print(f"   ✗ 최근 다룬 분야와 겹침({story.get('category')}) → 다른 이야기 선택")
            avoid += [c["title"] for c in chosen]
            articles = []
            continue
        # 예전에 게시했거나 예정인 글(기간 제한 없음, AI·경제·내 주제 모두)과 같은 소재면 절대 쓰지 않는다
        dup = [h for c in chosen for h in recent_overlap(cfg, c.get("title", ""), [c.get("url", "")], history)]
        if dup:
            print(f"   ✗ 예전 글과 겹침({dup[0].get('title', '')[:30]}) → 다른 이야기 선택")
            avoid += [c["title"] for c in chosen]
            articles = []
            continue
        articles = [a for a in (news.fetch_article(cfg, c) for c in chosen) if a]
        problem = "원문을 가져온 기사가 없어요." if not articles else verify.source_rule(articles)
        if articles and problem:  # 교차 확인 출처가 부족하면 신뢰 출처 안에서 검색해 보충
            print("   출처 보충: 같은 사건을 다룬 다른 신뢰 출처 검색")
            try:
                for url in writer.corroborate(cfg, articles, sorted(news.trusted_domains(cfg)))[:3]:
                    extra = news.fetch_article(cfg, {"url": url})
                    if extra and (extra.get("origin") or extra["source"]) not in \
                            {a.get("origin") or a["source"] for a in articles}:
                        articles.append(extra)
            except Exception as e:  # 웹 검색이 꺼져 있거나 실패해도 기존 흐름 유지
                print(f"   ⚠️  출처 보충 실패: {e}")
            problem = verify.source_rule(articles)
        for a in articles:
            print(f"   - [{a['tier']}] {a['source']}: {a['title']}")
        if not problem:
            break
        print(f"   ✗ 출처 조건 미충족: {problem}")
        avoid += [c["title"] for c in chosen]
        articles = []
    if not articles:
        msg = "출처 조건(공식 발표 1건 또는 언론사 2곳)을 만족하는 기사를 찾지 못해 이번 초안은 만들지 않았어요."
        print("✗ " + msg)
        if not args.local:
            import github_api as gh
            issue = gh.create_issue(f"[{date_label(date)}] 초안 없음 — 출처 조건 미충족",
                                    msg + "\n\n다시 시도하려면 Actions → 1. 초안 만들기 → Run workflow.", ["skipped"])
            gh.update_issue(issue["number"], state="closed")
        sys.exit(1)

    print("③ 카드뉴스 쓰기 + 출처 검증")
    post, result = writer.write_verified(cfg, topic, articles, story.get("angle", ""))
    print("   " + ("✅ 검증 통과" if result["passed"] else f"❌ 검증 실패: {result['problems']}"))

    slug = f"{date.isoformat()}-{topic}"
    draft_dir = (ROOT / "preview" / slug) if args.local else (DRAFTS / slug)
    draft_dir.mkdir(parents=True, exist_ok=True)
    data = {"date": date.isoformat(), "topic": topic, "version": 1, "post": post,
            "sources": [{k: a[k] for k in SOURCE_KEYS} for a in articles],
            "story": {"reason": story.get("reason", ""), "angle": story.get("angle", ""),
                      "category": story.get("category", "")},
            "verification": result}

    print("④ 이미지 만들기")
    paths = render_version(cfg, data, draft_dir)
    (draft_dir / "post.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.local:
        print(f"✅ 미리보기 완료: {draft_dir}")
        print(build_caption(post, data["sources"]))
        return

    import github_api as gh
    git_commit_push(f"draft: {slug}", [draft_dir])
    issue = gh.create_issue(issue_title(cfg, data), issue_body(cfg, data, paths, draft_dir), ["draft"])
    print(f"✅ 검토 요청 이슈: {issue['html_url']}")
    # --force로 새로 만든 경우: 같은 날짜의 예전 초안은 닫아서 두 개가 함께 게시되는 일을 막는다
    for old in same_day:
        gh.comment(old["number"], f"새 초안 #{issue['number']}으로 대체돼서 이 초안은 닫을게요.")
        gh.remove_label(old["number"], "approved")
        gh.add_labels(old["number"], ["skipped"])
        gh.update_issue(old["number"], state="closed")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if isinstance(e.code, str):  # sys.exit("이유")로 멈춘 경우도 이슈로 알림
            import github_api as gh
            gh.report_error(RuntimeError(e.code), "초안 만들기")
        raise
    except Exception as e:
        import github_api as gh
        gh.report_error(e, "초안 만들기")
        raise
