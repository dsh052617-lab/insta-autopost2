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


def post_datetime(cfg: dict, date: dt.date) -> dt.datetime:
    hh, mm = map(int, cfg["schedule"]["post_time"].split(":"))
    return dt.datetime(date.year, date.month, date.day, hh, mm, tzinfo=tz(cfg))


def next_post_slot(cfg: dict) -> tuple[dt.date, str]:
    """지금 이후 가장 가까운 게시 예정일과 주제."""
    days = {WEEKDAYS.index(k.lower()): v for k, v in cfg["schedule"]["days"].items()}
    current = now(cfg)
    for offset in range(0, 8):
        d = (current + dt.timedelta(days=offset)).date()
        if d.weekday() in days and post_datetime(cfg, d) > current:
            return d, days[d.weekday()]
    raise RuntimeError("config.yaml의 schedule.days를 확인해주세요.")


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
