import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auto_update as A  # noqa: E402
import collect_kr  # noqa: E402


def sh(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_remote(tmp: Path) -> str:
    """GitHub 대신 쓸 로컬 저장소 (data 파일 2개가 들어 있는 상태)."""
    bare = tmp / "remote.git"
    sh("init", "--bare", "-b", "main", str(bare), cwd=tmp)
    seed = tmp / "seed"
    sh("clone", str(bare), str(seed), cwd=tmp)
    (seed / "data").mkdir()
    (seed / "data" / "kr_financials.json.gz").write_bytes(b"annual-v1")
    (seed / "data" / "kr_quarterly.json.gz").write_bytes(b"quarter-v1")
    (seed / "app.py").write_text("print('app')\n")
    sh("add", ".", cwd=seed)
    sh("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-m", "init", cwd=seed)
    sh("push", "origin", "HEAD:main", cwd=seed)
    return str(bare)


def fake_collector(new_quarter: bytes | None, code: int = 0):
    script = ("import sys,pathlib\n"
              + (f"pathlib.Path('data/kr_quarterly.json.gz').write_bytes({new_quarter!r})\n" if new_quarter else "")
              + "print('분기 데이터 완료! 2669곳')\n"
              + f"sys.exit({code})\n")
    return [sys.executable, "-c", script]


def remote_file(bare: str, tmp: Path, rel: str) -> bytes:
    chk = tmp / "chk"
    if chk.exists():
        sh("fetch", "origin", cwd=chk)
        sh("reset", "--hard", "origin/main", cwd=chk)
    else:
        sh("clone", bare, str(chk), cwd=tmp)
    return (chk / rel).read_bytes()


def test_auto_update_pushes_new_data_and_skips_when_current(tmp_path, monkeypatch):
    bare = make_remote(tmp_path)
    here, clone, key = tmp_path / "mine", tmp_path / "home" / ".peerscope_repo", tmp_path / "key"
    here.mkdir()
    key.write_text("k" * 40)
    monkeypatch.setattr(A, "LOG", str(here / "auto_update.log"))

    # 새 분기 데이터가 생기면 커밋해서 올리고, 내 폴더 data 에도 복사
    assert A.run(bare, str(clone), str(here), fake_collector(b"quarter-v2"), str(key)) == 0
    assert remote_file(bare, tmp_path, "data/kr_quarterly.json.gz") == b"quarter-v2"
    assert (here / "data" / "kr_quarterly.json.gz").read_bytes() == b"quarter-v2"
    log = (here / "auto_update.log").read_text(encoding="utf-8")
    assert "GitHub에 올렸습니다" in log and "분기 데이터 완료" in log
    n_commits = sh("rev-list", "--count", "HEAD", cwd=tmp_path / "chk").strip()
    assert n_commits == "2"
    msg = sh("log", "-1", "--format=%s %an", cwd=tmp_path / "chk")
    assert msg.startswith("데이터 자동 갱신")

    # 바뀐 게 없으면 커밋하지 않음
    assert A.run(bare, str(clone), str(here), fake_collector(None), str(key)) == 0
    remote_file(bare, tmp_path, "data/kr_quarterly.json.gz")
    assert sh("rev-list", "--count", "HEAD", cwd=tmp_path / "chk").strip() == "2"
    assert "이미 최신" in (here / "auto_update.log").read_text(encoding="utf-8")


def test_auto_update_keeps_up_with_manual_uploads(tmp_path, monkeypatch):
    """사용자가 웹에서 코드를 따로 올려도, 다음 자동 갱신은 그 최신 상태 위에 데이터를 올린다."""
    bare = make_remote(tmp_path)
    here, clone, key = tmp_path / "mine", tmp_path / ".peerscope_repo", tmp_path / "key"
    here.mkdir()
    key.write_text("k" * 40)
    monkeypatch.setattr(A, "LOG", str(here / "auto_update.log"))
    assert A.run(bare, str(clone), str(here), fake_collector(None), str(key)) == 0
    seed = tmp_path / "seed"
    sh("pull", cwd=seed)
    (seed / "app.py").write_text("print('app v2')\n")
    sh("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-am", "web upload", cwd=seed)
    sh("push", "origin", "HEAD:main", cwd=seed)
    assert A.run(bare, str(clone), str(here), fake_collector(b"quarter-v3"), str(key)) == 0
    assert remote_file(bare, tmp_path, "app.py") == b"print('app v2')\n"
    assert remote_file(bare, tmp_path, "data/kr_quarterly.json.gz") == b"quarter-v3"


def test_auto_update_failures_are_logged(tmp_path, monkeypatch):
    bare = make_remote(tmp_path)
    here, clone = tmp_path / "mine", tmp_path / ".peerscope_repo"
    here.mkdir()
    monkeypatch.setattr(A, "LOG", str(here / "auto_update.log"))
    # 키가 없으면 시작하지 않음
    assert A.run(bare, str(clone), str(here), fake_collector(b"x"), str(tmp_path / "nokey")) == 1
    assert "인증키가 없습니다" in (here / "auto_update.log").read_text(encoding="utf-8")
    # 수집기가 멈추면 올리지 않음
    key = tmp_path / "key"
    key.write_text("k" * 40)
    assert A.run(bare, str(clone), str(here), fake_collector(b"half", code=1), str(key)) == 1
    assert remote_file(bare, tmp_path, "data/kr_quarterly.json.gz") == b"quarter-v1"
    assert "중간에 멈췄습니다" in (here / "auto_update.log").read_text(encoding="utf-8")


def test_setup_check_dry_run_push(tmp_path, monkeypatch):
    bare = make_remote(tmp_path)
    monkeypatch.setattr(A, "LOG", str(tmp_path / "auto_update.log"))
    assert A.setup_check(bare, str(tmp_path / ".peerscope_repo")) == 0
    assert "준비가 됐습니다" in (tmp_path / "auto_update.log").read_text(encoding="utf-8")


def test_collect_auto_mode_never_prompts(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(collect_kr, "KEY_FILE", str(tmp_path / "missing_key"))
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("input() called")))
    assert collect_kr.main(["--auto"]) == 1
    assert "저장된 DART 인증키가 없습니다" in capsys.readouterr().out
