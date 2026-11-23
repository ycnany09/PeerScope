"""피어스코프 자동 갱신.

윈도우 작업 스케줄러가 매주 이 스크립트를 실행한다.
1) GitHub 저장소를 깨끗한 복사본(~/.peerscope_repo)으로 최신화
2) 그 안에서 수집기(collect_kr.py --auto)를 실행 (이미 최신이면 몇 초 만에 끝남)
3) 데이터 파일이 바뀌었으면 커밋해서 GitHub에 올림 → 공개 사이트가 새 데이터로 갱신
4) 이 폴더의 data 에도 복사 (내 PC에서 run_app.bat 으로 볼 때도 최신)

DART가 해외 서버 접속을 막아서 클라우드(GitHub Actions 등)에서는 돌릴 수 없고, 한국에 있는 내 PC에서 돈다.
기록은 이 폴더의 auto_update.log 에 남는다.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/ycnany09/PeerScope.git"
CLONE = os.path.join(os.path.expanduser("~"), ".peerscope_repo")
LOG = os.path.join(HERE, "auto_update.log")
DATA_FILES = ("data/kr_financials.json.gz", "data/kr_quarterly.json.gz")
KEY_FILE = os.path.join(os.path.expanduser("~"), ".peerscope_dart_key")


class AutoError(Exception):
    pass


def log(msg: str, path: str | None = None):
    path = path or LOG
    line = f"[{datetime.now():%Y-%m-%d %H:%M}] {msg}"
    print(line, flush=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def git(*args, cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise AutoError(f"git {' '.join(args[:2])} 실패: {(p.stderr or p.stdout).strip()[-400:]}")
    return p


def branch_of(clone: str) -> str:
    p = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=clone, check=False)
    return p.stdout.strip().split("/", 1)[-1] if p.returncode == 0 and p.stdout.strip() else "main"


def sync(repo_url: str, clone: str) -> str:
    """복사본을 GitHub 최신 상태로 맞춘다. 지난번에 못 올린 데이터 커밋이 있으면 먼저 올려 본다."""
    if not os.path.isdir(os.path.join(clone, ".git")):
        os.makedirs(os.path.dirname(clone) or ".", exist_ok=True)
        log("GitHub 저장소를 처음 내려받습니다.")
        git("clone", repo_url, clone, cwd=os.path.dirname(clone) or ".")
    git("fetch", "origin", cwd=clone)
    br = branch_of(clone)
    ahead = git("rev-list", "--count", f"origin/{br}..HEAD", cwd=clone, check=False).stdout.strip()
    if ahead not in ("", "0"):
        if git("rebase", f"origin/{br}", cwd=clone, check=False).returncode == 0 and \
                git("push", "origin", f"HEAD:{br}", cwd=clone, check=False).returncode == 0:
            log("지난번에 올리지 못한 데이터를 올렸습니다.")
        else:
            git("rebase", "--abort", cwd=clone, check=False)
    git("checkout", "-B", br, f"origin/{br}", cwd=clone, check=False)
    git("reset", "--hard", f"origin/{br}", cwd=clone)
    return br


def identity(repo_url: str, clone: str) -> list[str]:
    """커밋 작성자. 사용자가 git 에 이름을 설정했으면 그대로, 없으면 저장소 주인 이름으로."""
    name = git("config", "user.name", cwd=clone, check=False).stdout.strip()
    email = git("config", "user.email", cwd=clone, check=False).stdout.strip()
    if name and email:
        return []
    owner = repo_url.rstrip("/").removesuffix(".git").split("/")[-2] if "/" in repo_url else "peerscope"
    return ["-c", f"user.name={name or 'PeerScope 자동 갱신'}",
            "-c", f"user.email={email or owner + '@users.noreply.github.com'}"]


def run(repo_url: str = REPO_URL, clone: str = CLONE, here: str = HERE, collect_cmd: list[str] | None = None,
        key_file: str = KEY_FILE) -> int:
    """한 번 갱신. 반환: 0 성공(올림 또는 이미 최신), 1 실패."""
    try:
        if not shutil.which("git"):
            raise AutoError("Git이 설치되어 있지 않습니다. git-scm.com 에서 Git for Windows를 설치하세요.")
        if not os.path.exists(key_file):
            raise AutoError("저장된 DART 인증키가 없습니다. collect_kr.bat을 한 번 직접 실행해서 키를 저장하세요.")
        br = sync(repo_url, clone)
        cmd = collect_cmd or [sys.executable, os.path.join(clone, "collect_kr.py"), "--auto"]
        log("수집기를 실행합니다. (이미 최신이면 바로 끝납니다)")
        p = subprocess.run(cmd, cwd=clone, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        tail = [ln for ln in (p.stdout or "").splitlines() if ln.strip()][-3:]
        for ln in tail:
            log("  " + ln.strip())
        if p.returncode != 0:
            raise AutoError("수집기가 중간에 멈췄습니다. 다음 실행 때 이어서 수집합니다. "
                            + (p.stderr or "").strip()[-300:])
        changed = git("status", "--porcelain", "--", *DATA_FILES, cwd=clone).stdout.strip()
        if not changed:
            log("새 데이터가 없습니다. 이미 최신입니다.")
        else:
            git("add", "--", *DATA_FILES, cwd=clone)
            git(*identity(repo_url, clone), "commit", "-m", f"데이터 자동 갱신 ({datetime.now():%Y-%m-%d})", cwd=clone)
            git("push", "origin", f"HEAD:{br}", cwd=clone)
            log("새 데이터를 GitHub에 올렸습니다. 공개 사이트에 몇 분 안에 반영됩니다.")
        for rel in DATA_FILES:  # 내 PC에서 보는 화면도 최신으로
            src = os.path.join(clone, rel)
            if os.path.exists(src):
                os.makedirs(os.path.join(here, "data"), exist_ok=True)
                shutil.copy2(src, os.path.join(here, rel))
        return 0
    except AutoError as e:
        log(f"실패: {e}")
        return 1


def setup_check(repo_url: str = REPO_URL, clone: str = CLONE) -> int:
    """설정 확인: 저장소를 받고, GitHub 로그인이 되어 있는지(올릴 권한) 시험한다. 처음이면 로그인 창이 뜬다."""
    try:
        if not shutil.which("git"):
            raise AutoError("Git이 설치되어 있지 않습니다. git-scm.com 에서 Git for Windows를 설치한 뒤 다시 실행하세요.")
        br = sync(repo_url, clone)
        log("GitHub 로그인 확인 중입니다. 로그인 창이 뜨면 GitHub 계정으로 로그인하세요.")
        p = git("push", "--dry-run", "origin", f"HEAD:{br}", cwd=clone, check=False)
        if p.returncode != 0:
            raise AutoError("GitHub에 올릴 권한을 확인하지 못했습니다. 로그인 후 다시 실행하세요. "
                            + (p.stderr or "").strip()[-300:])
        log("확인 완료: 자동 갱신 준비가 됐습니다.")
        return 0
    except AutoError as e:
        log(f"실패: {e}")
        return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="피어스코프 자동 갱신")
    ap.add_argument("--setup", action="store_true", help="처음 설정할 때: 저장소 받기 + GitHub 로그인 확인")
    ap.add_argument("--repo", default=REPO_URL, help="GitHub 저장소 주소")
    args = ap.parse_args(argv)
    return setup_check(args.repo) if args.setup else run(args.repo)


if __name__ == "__main__":
    sys.exit(main())
