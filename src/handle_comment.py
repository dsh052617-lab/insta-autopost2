"""초안 이슈에 단 댓글(승인 / 수정: … / 지금 게시 / 취소)을 처리."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import github_api as gh  # noqa: E402
import writer  # noqa: E402
from common import ROOT, date_label, git_commit_push, load_config, slot_time  # noqa: E402
from draft import SOURCE_KEYS, fetch_articles, issue_body, issue_title, render_version  # noqa: E402

BLOCKED = ("❌ 출처 검증을 통과하지 못한 초안이라 승인·게시할 수 없어요.\n"
           "`수정: 원문에 없는 내용은 빼줘`처럼 고치거나 `취소`해 주세요.")


def main() -> None:
    cfg = load_config()
    number = int(os.environ["ISSUE_NUMBER"])
    text = os.environ.get("COMMENT_BODY", "").strip()
    first = text.splitlines()[0].strip() if text else ""
    issue = gh.get_issue(number)
    marker = gh.read_marker(issue)
    if not marker or not marker.get("dir"):
        return
    if not first.startswith(("승인", "취소", "수정", "날짜")) and not first.replace(" ", "").startswith("지금게시"):
        return  # 명령이 아닌 일반 댓글은 무시
    draft_dir = ROOT / marker["dir"]
    post_file = draft_dir / "post.json"
    if not post_file.exists():
        gh.comment(number, f"⚠️ 초안 파일({marker['dir']}/post.json)을 저장소에서 찾지 못했어요. "
                           "초안을 다시 만들어 주세요 (Actions → 1. 초안 만들기).")
        return
    data = json.loads(post_file.read_text(encoding="utf-8"))
    passed = data.get("verification", {}).get("passed", False)
    when = f"{date_label(dt.date.fromisoformat(marker['date']))} {slot_time(cfg, marker.get('topic'))}"

    if first.startswith("승인"):
        if not passed:
            gh.comment(number, BLOCKED)
            return
        if marker.get("custom"):  # 내 주제는 승인 즉시 게시
            from publish import publish_or_report as publish_issue
            gh.comment(number, "✅ 승인됐어요. 지금 인스타에 올릴게요…")
            publish_issue(cfg, issue)
            return
        from common import now, post_datetime
        slot = post_datetime(cfg, dt.date.fromisoformat(marker["date"]), marker.get("topic"))
        current = now(cfg)
        if slot.date() < current.date():  # 게시일이 이미 지난 초안
            gh.comment(number, f"📅 게시일({when})이 지나서 승인하지 않았어요. "
                               "`날짜: 11/20`처럼 새 날짜를 정한 뒤 다시 `승인`해 주세요.")
            return
        gh.add_labels(number, ["approved"])
        if current > slot:  # 오늘 예정 시각이 이미 지남 → 게시 작업을 바로 한 번 더 돌린다
            gh.comment(number, f"✅ 승인됐어요. 예정 시각({when})이 지나서 곧바로 올릴게요 (2~5분).")
            gh.dispatch_publish()
        else:
            gh.comment(number, f"✅ 승인됐어요. {when}에 인스타에 올라가요.")
            if (slot - current).total_seconds() <= 40 * 60:
                # 게시 시각이 가까우면 게시 작업을 직접 시작해 둔다 (예정 시각까지 기다렸다 올림).
                # GitHub 예약 실행이 늦거나 빠져도 제시간에 올라가게 하는 안전장치.
                try:
                    gh.dispatch_publish()
                except Exception as e:
                    print(f"(게시 작업 시작 실패 — 예약 실행이 맡아요: {e})")

    elif first.replace(" ", "").startswith("지금게시"):
        if not passed:
            gh.comment(number, BLOCKED)
            return
        from publish import publish_or_report as publish_issue
        gh.comment(number, "🚀 지금 게시할게요…")
        publish_issue(cfg, issue)

    elif first.startswith("취소"):
        gh.add_labels(number, ["skipped"])
        gh.update_issue(number, state="closed")
        gh.comment(number, "이번 회차는 건너뛸게요.")

    elif first.startswith("날짜"):  # 게시 날짜만 바꾸기 (예: `날짜: 11/16`) — 내용은 그대로, API 요금 없음
        import re
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})[/.](\d{1,2})", first)
        if not m:
            gh.comment(number, "날짜를 `날짜: 11/16` 또는 `날짜: 2026-11-16`처럼 적어주세요.")
            return
        today = dt.date.today()
        new = (dt.date(int(m[1]), int(m[2]), int(m[3])) if m[1]
               else dt.date(today.year, int(m[4]), int(m[5])))
        if new < today - dt.timedelta(days=1):
            new = dt.date(new.year + 1, new.month, new.day)
        data.update(date=new.isoformat(), version=data["version"] + 1)
        paths = render_version(cfg, data, draft_dir)  # 표지 날짜도 새로 그림
        (draft_dir / "post.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        git_commit_push(f"reschedule: {marker['dir']} → {new}", [draft_dir])
        body = issue_body(cfg, data, paths, draft_dir).replace(
            f'"date": "{marker["date"]}"', f'"date": "{new.isoformat()}"')
        gh.update_issue(number, title=issue_title(cfg, data), body=body)
        state = "승인 상태는 그대로예요." if "approved" in gh.label_names(issue) else "확인 후 `승인`해 주세요."
        gh.comment(number, f"📅 게시 날짜를 {date_label(new)} {slot_time(cfg, data['topic'])}로 바꿨어요. {state}")

    elif first.startswith("수정"):
        feedback = text[len("수정"):].lstrip(" :：").strip()
        if not feedback:
            gh.comment(number, "어떻게 고칠지 함께 적어주세요. 예: `수정: 제목을 덜 자극적으로`")
            return
        gh.comment(number, "✏️ 수정 중이에요. 원문을 다시 가져와 검증까지 하고 올릴게요 (1~2분).")
        articles = fetch_articles(cfg, data["sources"])
        if not articles:
            gh.comment(number, "⚠️ 원문 사이트에 접속하지 못해 지금은 수정할 수 없어요. 잠시 뒤 같은 댓글을 다시 달아주세요.")
            return
        if len(articles) < len(data["sources"]):
            gh.comment(number, "⚠️ 일부 원문을 다시 가져오지 못해, 확인된 원문만으로 검증해요.")
        post, result = writer.write_verified(cfg, data["topic"], articles, base=data["post"], feedback=feedback)
        data.update(post=post, verification=result, version=data["version"] + 1,
                    sources=[{k: a[k] for k in SOURCE_KEYS} for a in articles])
        paths = render_version(cfg, data, draft_dir)
        (draft_dir / "post.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        git_commit_push(f"revise: {marker['dir']} v{data['version']}", [draft_dir])
        gh.remove_label(number, "approved")  # 내용이 바뀌었으니 다시 승인 받기
        gh.update_issue(number, title=issue_title(cfg, data), body=issue_body(cfg, data, paths, draft_dir))
        if result["passed"]:
            gh.comment(number, f"🆕 새 버전(v{data['version']})이 출처 검증을 통과했어요. 괜찮으면 `승인`이라고 달아주세요.")
        else:
            gh.comment(number, f"⚠️ 새 버전(v{data['version']})도 출처 검증을 통과하지 못했어요. 본문의 문제 목록을 확인해주세요.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if not getattr(e, "reported", False):
            gh.report_error(e, "댓글 처리", int(os.environ.get("ISSUE_NUMBER", "0") or 0))
        raise
