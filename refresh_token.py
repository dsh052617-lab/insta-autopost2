"""인스타 토큰(60일 유효)을 연장하고 GitHub Secret을 새 값으로 바꾼다.
GH_PAT 시크릿(저장소 Secrets 쓰기 권한)이 있어야 자동 교체돼요."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import instagram  # noqa: E402


def main() -> None:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        print("ℹ️  IG_ACCESS_TOKEN 시크릿이 아직 없어요. 등록 전에는 할 일이 없어요.")
        return
    if not instagram.is_instagram_login_token(token):
        print("✅ 통합 로그인(시스템 사용자) 토큰은 만료가 없어서 연장할 필요가 없어요.")
        return
    data = instagram.refresh_token(token)
    new = data["access_token"]
    print(f"::add-mask::{new}")
    days = int(data.get("expires_in", 0)) // 86400
    if not os.environ.get("GH_TOKEN"):
        print(f"⚠️  GH_PAT 시크릿이 없어 저장은 못 했어요. 기존 토큰 만료일만 {days}일 연장됐어요.")
        return
    subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"]],
                   input=new.encode(), check=True)
    print(f"✅ 토큰 갱신 완료 (앞으로 {days}일 유효)")


if __name__ == "__main__":
    main()
