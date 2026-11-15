"""픽스(비서 앱)에 보여줄 인스타 초안 목록을 만든다.

예약 작업(Claude)이 실행: `python3 src/pix_sync.py [--days 7]`
→ 표준 출력으로 JSON 배열 [{"id": "<이슈 번호>", "data": {...}}, ...]
   각 항목을 픽스 ArtifactData 컬렉션 "insta"의 문서로 그대로 저장하면 된다.

GitHub 정보는 `gh api`(REST)로 읽고, 원고는 저장소의 drafts/*/post.json에서 읽는다
(실행 전에 `git pull`로 최신 상태로 맞출 것). Claude API는 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, load_config, slot_time  # noqa: E402

REPO = "dsh052617-lab/insta-autopost2"
MARKER_RE = re.compile(r"<!-- insta-draft: (\{.*?\}) -->", re.S)
LINK_RE = re.compile(r"https://www\.instagram\.com/\S+")
POST_KEYS = ("cover_kicker", "cover_title", "cover_subtitle", "slides", "takeaways", "question",
             "caption", "hashtags", "needs_disclaimer")


def gh(path: str):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out or "null")


def status_of(issue: dict) -> str:
    labels = {l["name"] for l in issue.get("labels", [])}
    if "published" in labels:
        return "published"
    if "skipped" in labels or issue["state"] == "closed":
        return "cancelled"
    if "approved" in labels:
        return "approved"
    if "draft" in labels:
        return "draft"
    return "making"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    cfg = load_config()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = gh(f"repos/{REPO}/issues?state=all&per_page=40&sort=updated&direction=desc&since={since}") or []
    out = []
    for it in issues:
        if "pull_request" in it:
            continue
        title = it.get("title") or ""
        labels = {l["name"] for l in it.get("labels", [])}
        m = MARKER_RE.search(it.get("body") or "")
        if not m and not title.startswith("직접") and "draft" not in labels:
            continue  # 설정 점검·오류 이슈 등은 제외
        data = {"issue": it["number"], "url": it["html_url"], "status": status_of(it),
                "updatedAt": it.get("updated_at"), "title": title}
        if m:
            try:
                mk = json.loads(m.group(1))
            except ValueError:
                mk = {}
            f = ROOT / mk.get("dir", "") / "post.json"
            if mk.get("dir") and f.exists():
                d = json.loads(f.read_text(encoding="utf-8"))
                topic = d.get("topic", "")
                custom = bool(d.get("custom"))
                ver = d.get("verification") or {}
                data.update({
                    "topic": topic, "custom": custom, "date": d.get("date", ""),
                    "time": "승인 즉시" if custom else slot_time(cfg, topic),
                    "label": cfg["topics"].get(topic, {}).get("label", topic),
                    "version": d.get("version", 1),
                    "verified": bool(ver.get("passed")),
                    "problems": [str(p)[:160] for p in (ver.get("problems") or [])][:5],
                    "post": {k: d.get("post", {}).get(k) for k in POST_KEYS},
                    "sources": [{k: s.get(k, "") for k in ("title", "source", "url", "published", "tier")}
                                for s in d.get("sources", [])],
                    "cardsUrl": it["html_url"],
                })
        if data["status"] == "published":
            try:
                for c in gh(f"repos/{REPO}/issues/{it['number']}/comments?per_page=50") or []:
                    lk = LINK_RE.search(c.get("body") or "")
                    if lk:
                        data["permalink"] = lk.group(0).rstrip(").")
            except subprocess.CalledProcessError:
                pass
        out.append({"id": str(it["number"]), "data": data})
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
