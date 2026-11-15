"""공통 유틸: 설정, 경로, 시간, git, 기록."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "drafts"
HISTORY = ROOT / "data" / "history.json"

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def tz(cfg: dict) -> ZoneInfo:
    return ZoneInfo(cfg["schedule"].get("timezone", "Asia/Seoul"))


def now(cfg: dict) -> dt.datetime:
    return dt.datetime.now(tz(cfg))


def slot_time(cfg: dict, topic: str | None = None) -> str:
    """주제별 게시 시각 'HH:MM' (slots가 없으면 post_time)."""
    return (cfg["schedule"].get("slots") or {}).get(topic or "", cfg["schedule"].get("post_time", "20:00"))


def post_datetime(cfg: dict, date: dt.date, topic: str | None = None) -> dt.datetime:
    hh, mm = map(int, slot_time(cfg, topic).split(":"))
    return dt.datetime(date.year, date.month, date.day, hh, mm, tzinfo=tz(cfg))


def _slots(cfg: dict) -> list[tuple[int, str]]:
    """(요일 0=월…6=일, 주제) 목록. slots가 있으면 매일, 없으면 days 설정."""
    if cfg["schedule"].get("slots"):
        return [(wd, t) for wd in range(7) for t in cfg["schedule"]["slots"]]
    return [(WEEKDAYS.index(k.lower()), v) for k, v in cfg["schedule"]["days"].items()]


def next_post_slot(cfg: dict, topic: str | None = None) -> tuple[dt.date, str]:
    """지금 이후 가장 가까운 게시 예정 (날짜, 주제). topic을 주면 그 주제의 다음 회차."""
    current = now(cfg)
    start = cfg["schedule"].get("start_date")
    start = dt.date.fromisoformat(str(start)) if start else None
    best = None
    for offset in range(0, 40):
        d = (current + dt.timedelta(days=offset)).date()
        if start and d < start:
            continue
        for wd, t in _slots(cfg):
            if wd != d.weekday() or (topic and t != topic):
                continue
            when = post_datetime(cfg, d, t)
            if when > current and (best is None or when < best[0]):
                best = (when, d, t)
        if best:
            return best[1], best[2]
    raise RuntimeError("config.yaml의 schedule을 확인해주세요.")


def date_label(date: dt.date) -> str:
    return f"{date.month}/{date.day}({WEEKDAY_KO[date.weekday()]})"


def repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")


def branch() -> str:
    return os.environ.get("GITHUB_REF_NAME") or "main"


def raw_url(path: Path) -> str:
    rel = path.resolve().relative_to(ROOT).as_posix()
    return f"https://raw.githubusercontent.com/{repo()}/{branch()}/{rel}"


def load_history() -> list[dict]:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return []


def save_history(items: list[dict]) -> None:
    HISTORY.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def git_commit_push(message: str, paths: list[Path | str]) -> None:
    """GitHub Actions 안에서만 커밋·푸시 (로컬 테스트 땐 건너뜀)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        print(f"[local] git 커밋 생략: {message}")
        return
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, cwd=ROOT)
    subprocess.run(["git", "config", "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com"], check=True, cwd=ROOT)
    subprocess.run(["git", "add", *[str(p) for p in paths]], check=True, cwd=ROOT)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=ROOT)
    for _ in range(3):
        if subprocess.run(["git", "push"], cwd=ROOT).returncode == 0:
            return
        subprocess.run(["git", "pull", "--rebase"], check=True, cwd=ROOT)
    raise RuntimeError("git push 실패")


def append_history_and_push(entry: dict, message: str) -> None:
    """게시 기록 한 줄 추가. 여러 작업이 동시에 기록해도 서로 덮어쓰지 않게:
    최신본을 받아 → 추가 → 푸시, 충돌하면 내 커밋을 되돌리고 처음부터 다시 (최대 5번)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        save_history(load_history() + [entry])
        print(f"[local] git 커밋 생략: {message}")
        return
    run = lambda *a, **k: subprocess.run(list(a), cwd=ROOT, **k)  # noqa: E731
    run("git", "config", "user.name", "github-actions[bot]", check=True)
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", check=True)
    for attempt in range(5):
        run("git", "fetch", "origin", branch())
        run("git", "reset", "--hard", f"origin/{branch()}", check=True)
        items = load_history()
        if entry.get("media_id") and any(h.get("media_id") == entry["media_id"] for h in items):
            return  # 이미 기록됨
        save_history(items + [entry])
        run("git", "add", str(HISTORY), check=True)
        run("git", "commit", "-m", message, check=True)
        if run("git", "push", "origin", f"HEAD:{branch()}").returncode == 0:
            return
        import time
        time.sleep(3 * (attempt + 1))
    raise RuntimeError("게시 기록 푸시 실패 (5번 시도)")


# ── 내용 겹침 검사 (기간 제한 없음, AI·경제·내 주제 모두) ──
def _norm_title(t: str) -> str:
    import re as _re
    return _re.sub(r"[^0-9A-Za-z가-힣]", "", (t or "").replace("\\n", "").replace("\n", "")).lower()


def _tokens(t: str) -> set:
    import re as _re
    return {w for w in _re.findall(r"[0-9A-Za-z가-힣]{2,}", (t or "").replace("\\n", " ").replace("\n", " ").lower())}


def recent_overlap(cfg: dict, title: str, urls: list[str], others: list[dict], days: int | None = None) -> list[dict]:
    """게시됐거나 게시 예정인 글 중(기본: 기간 제한 없음), 같은 출처 기사를 쓰거나 제목이 비슷한 것을 돌려준다."""
    import difflib
    cutoff = (now(cfg).date() - dt.timedelta(days=days)).isoformat() if days else "0000"
    mine_t, mine_k, mine_u = _norm_title(title), _tokens(title), set(urls)
    hits = []
    for o in others:
        if (o.get("date") or "9999") < cutoff:
            continue
        ot = o.get("title", "")
        same_url = bool(mine_u & set(o.get("urls", [])))
        ratio = difflib.SequenceMatcher(None, mine_t, _norm_title(ot)).ratio() if mine_t and ot else 0
        ok = _tokens(ot)
        jac = len(mine_k & ok) / max(1, len(mine_k | ok))
        if same_url or ratio >= 0.55 or jac >= 0.5:
            hits.append({**o, "why": "같은 출처 기사" if same_url else "제목·소재가 비슷함"})
    return hits
