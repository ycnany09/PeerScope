import gzip
import json
import sys
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import collect_kr  # noqa: E402
import dart  # noqa: E402
import fake_dart as F  # noqa: E402

H = F.FakeHttp


def run(tmp_path, http=H, **kw):
    out, part = tmp_path / "data" / "kr.json.gz", tmp_path / "data" / "_p.json"
    data = collect_kr.collect("K", 2025, http=http, out=str(out), part=str(part), pause=0, log=lambda *a: None, **kw)
    return data, out, part


def test_collect_all(tmp_path):
    data, out, part = run(tmp_path)
    assert out.exists() and not part.exists()
    with gzip.open(out, "rt", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["base_year"] == 2025 and saved["collected_at"].startswith("20")
    comp = saved["companies"]
    assert {c["name"] for c in saved["corps"]} == {"A&B컴퍼니", "삼성전자", "씨제이이엔엠", "제이와이피엔터테인먼트", "하이브"}
    assert comp["00265324"]["status"] == "ok" and comp["00258689"]["status"] == "nodata"
    assert comp["01204056"]["fell_back"] is True and comp["01204056"]["fs"] == "OFS"
    assert "08888888" not in comp  # 비상장 무신사는 수집 대상 아님


def test_cache_matches_live(tmp_path):
    data, _, _ = run(tmp_path)
    corp = {"code": "00265324", "name": "씨제이이엔엠", "stock": "035760"}
    live = dart.analyze_company("K", corp, 2025, "CFS", http=H)
    cached = dart.company_from_cache(data["companies"]["00265324"], corp, 2025, 2025)
    for y in range(2021, 2026):
        assert cached["years"][y]["amount"] == live["years"][y]["amount"]
        assert cached["years"][y]["ratio"] == live["years"][y]["ratio"]
    assert cached["links"][2025] == live["links"][2025] and cached["missing"] == live["missing"]
    # 기준연도를 2024로 바꾸면 2020은 비어 있음
    c24 = dart.company_from_cache(data["companies"]["00265324"], corp, 2024, 2025)
    assert c24["years"][2024]["amount"]["rev"] == pytest.approx(4.5e12) and "2020년 수치 없음" in c24["older_note"]
    with pytest.raises(dart.DartError) as e:
        dart.company_from_cache(data["companies"]["00265324"], corp, 2026, 2025)
    assert e.value.status == "CACHE"


def test_resume(tmp_path):
    part = tmp_path / "data" / "_p.json"
    part.parent.mkdir(parents=True)
    part.write_text(json.dumps({"base_year": 2025, "companies": {"00265324": {"status": "nodata"}}}), encoding="utf-8")
    F.CALLS.clear()
    data, _, _ = run(tmp_path)
    assert not any(p.get("corp_code") == "00265324" for _, p in F.CALLS)  # 이미 끝난 회사는 다시 안 부름
    assert data["companies"]["00265324"] == {"status": "nodata"}


def test_stop_on_limit_and_resume_file(tmp_path):
    class Limit:
        @staticmethod
        def get(url, params=None, timeout=None, headers=None):
            if url.endswith("corpCode.xml"):
                return F.fake_get(url, params=params, timeout=timeout)
            return F.Resp(js={"status": "020", "message": "요청 제한을 초과하였습니다."})
    with pytest.raises(collect_kr.Stop) as e:
        run(tmp_path, http=Limit)
    assert "내일" in str(e.value)
    assert (tmp_path / "data" / "_p.json").exists()


def test_bad_key_stops(tmp_path):
    with pytest.raises(collect_kr.Stop) as e:
        collect_kr.collect("BAD", 2025, http=H, out=str(tmp_path / "o.gz"), part=str(tmp_path / "p.json"), pause=0,
                           log=lambda *a: None)
    assert "등록되지 않은" in str(e.value)


def test_read_key(tmp_path, monkeypatch):
    monkeypatch.setattr(collect_kr, "KEY_FILE", str(tmp_path / "keyfile"))
    answers = iter(["  " + "a" * 40 + " ", "y"])
    assert collect_kr.read_key(ask=lambda _: next(answers)) == "a" * 40
    assert (tmp_path / "keyfile").read_text() == "a" * 40
    assert collect_kr.read_key(ask=lambda _: pytest.fail("묻지 않아야 함")) == "a" * 40
    (tmp_path / "keyfile").unlink()
    with pytest.raises(collect_kr.Stop):
        collect_kr.read_key(ask=lambda _: "short")


def test_default_year():
    from datetime import date
    assert collect_kr.default_year(date(2026, 11, 20)) == 2025
    assert collect_kr.default_year(date(2026, 3, 1)) == 2024


def test_app_reads_cache_without_dart(tmp_path, monkeypatch):
    _, out, _ = run(tmp_path)

    def no_dart(url, params=None, timeout=None, headers=None):
        assert "opendart" not in url, "캐시 모드에서는 DART에 접속하면 안 됨"
        return F.fake_get(url, params=params, timeout=timeout, headers=headers)
    monkeypatch.setattr(requests, "get", no_dart)
    monkeypatch.setenv("PEERSCOPE_KR_CACHE", str(out))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.secrets["SEC_USER_AGENT"] = "Kim Jimin jimin@example.com"   # DART 키는 없음
    at.run()
    assert not at.exception, at.exception
    assert not at.multiselect[0].disabled
    assert any("국내 데이터:" in c.value and "2025년 사업보고서까지" in c.value for c in at.caption)
    at.multiselect[0].set_value(["씨제이이엔엠 (035760)", "하이브 (352820)", "제이와이피엔터테인먼트 (035900)"])
    at.multiselect[1].set_value(["마이크론 · MICRON TECHNOLOGY INC (MU)"])
    at.button[0].click().run()
    F.annual(at, 2025)
    assert not at.exception, at.exception
    t = " ".join(m.value for m in at.markdown)
    assert "<td>50,000</td>" in t and "<td>15.0%</td>" in t and "MICRON TECHNOLOGY INC" in t
    assert "<b>제이와이피엔터테인먼트</b> 조회 제외" in t
    assert "rcpNo=20260310000111" in t
