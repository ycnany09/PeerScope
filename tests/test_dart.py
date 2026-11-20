import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import dart  # noqa: E402
import fake_dart as F  # noqa: E402

H = F.FakeHttp


def test_corp_list_and_listed():
    corps = dart.fetch_corp_list("K", http=H)
    assert len(corps) == 6
    assert corps[5]["name"] == "A&B컴퍼니" and corps[5]["eng"] == ""
    assert corps[4]["stock"] == ""  # 비상장 공백 → 빈 값
    names = [c["name"] for c in dart.listed(corps)]
    assert "무신사" not in names and names == sorted(names)


def test_bad_key_message():
    with pytest.raises(dart.DartError) as e:
        dart.fetch_corp_list("BAD", http=H)
    assert e.value.status == "010" and "등록되지 않은 키" in e.value.message


def test_extract_sce_ignored_and_names():
    rows = [F.row("SCE", "ifrs_ProfitLoss", "당기순이익", "999", "", ""),
            F.row("IS", "ifrs_ProfitLoss", "당기순이익", "35", "15", "")]
    assert dart.extract_accounts(rows)["net"]["cur"] == 35
    h = dart.extract_accounts(F.FIN[("01204056", "2025", "OFS")]["list"])
    assert h["rev"]["cur"] == 2e12 and h["ca"] is None


def test_owner_share_row_not_used():
    a = dart.extract_accounts(F.FIN[("00265324", "2025", "CFS")]["list"])
    assert a["net"]["cur"] == pytest.approx(1e11)
    assert a["op"]["prev"] == pytest.approx(-5e10)


def test_ratios():
    v = {"rev": 300, "op": 30, "net": 35, "assets": 500, "liab": 100, "equity": 400, "ca": 200, "cl": 80}
    r = dart.ratios(v, {"rev": 260})
    assert r["growth"] == pytest.approx(40 / 260)
    assert r["op_margin"] == 0.1 and r["debt"] == 0.25 and r["current"] == 2.5
    # 듀폰 항등식: ROE = 순이익률 × 회전율 × 레버리지
    assert r["roe"] == pytest.approx(r["net_margin"] * r["turnover"] * r["leverage"])
    z = dart.ratios({"equity": -10, "liab": 50, "net": 5, "assets": 40})
    assert z["debt"] is None and z["roe"] is None and z["leverage"] is None
    assert dart.ratios({"rev": 10}, {"rev": 0})["growth"] is None


def test_growth_uses_abs_of_negative_base():
    assert dart.ratios({"rev": 5}, {"rev": -10})["growth"] == pytest.approx(1.5)


def test_parse_amount():
    assert dart.parse_amount("-") is None and dart.parse_amount("") is None
    assert dart.parse_amount("1,234") == 1234 and dart.parse_amount(None) is None
    assert dart.parse_amount("abc") is None


def test_analyze_five_years_cj():
    c = dart.analyze_company("K", {"code": "00265324", "name": "씨제이이엔엠", "stock": "035760"}, 2025, "CFS", http=H)
    assert sorted(c["years"]) == [2021, 2022, 2023, 2024, 2025]
    rev = {y: c["years"][y]["amount"]["rev"] for y in c["years"]}
    # 2023은 두 보고서에 다 있는데 최근(2025) 보고서 값 4조를 써야 함 (2023 보고서엔 3.9조)
    assert rev[2023] == pytest.approx(4e12)
    assert rev[2022] == pytest.approx(3.5e12) and rev[2021] == pytest.approx(3.0e12)
    assert c["years"][2021]["ratio"]["growth"] is None
    assert c["years"][2022]["ratio"]["growth"] == pytest.approx(0.5 / 3.0)
    assert c["src"][2025] == "20260310000111" and c["src"][2021] == "20240315000222"
    assert c["fs"] == "CFS" and not c["fell_back"] and c["older_note"] == "" and c["missing"] == []
    # 두 번째 보고서는 첫 번째와 같은 구분(CFS)으로만 요청
    calls = [p for u, p in F.CALLS if p.get("corp_code") == "00265324" and p.get("bsns_year") == "2023"]
    assert {p["fs_div"] for p in calls} == {"CFS"}


def test_analyze_fallback_and_missing_older():
    c = dart.analyze_company("K", {"code": "01204056", "name": "하이브", "stock": "352820"}, 2025, "CFS", http=H)
    assert c["fs"] == "OFS" and c["fell_back"]
    assert "유동자산" in c["missing"] and "유동부채" in c["missing"]
    assert "2021~2022년 수치 없음" in c["older_note"]
    assert c["years"][2022]["amount"] == {} and c["years"][2023]["amount"]["rev"] == 1.5e12


def test_analyze_no_data():
    with pytest.raises(dart.DartError) as e:
        dart.analyze_company("K", {"code": "00258689", "name": "JYP"}, 2025, "CFS", http=H)
    assert e.value.status == "013"


def test_key_error_stops_immediately():
    class Bad:
        n = 0

        @staticmethod
        def get(url, params=None, timeout=None):
            Bad.n += 1
            return F.Resp(js={"status": "010", "message": "등록되지 않은 키입니다."})
    with pytest.raises(dart.DartError):
        dart.fetch_statements("K", "x", 2025, ("CFS", "OFS"), http=Bad)
    assert Bad.n == 1


def test_summary_lines():
    cs = [dart.analyze_company("K", {"code": c, "name": n}, 2025, "CFS", http=H)
          for c, n in (("00265324", "씨제이이엔엠"), ("01204056", "하이브"))]
    lines = dart.summary_lines(cs)
    assert len(lines) == len(dart.RATIOS)
    assert "영업이익률** — 가장 높음: 하이브 15.0% · 가장 낮음: 씨제이이엔엠 4.0%" in lines[1]
    assert "부채비율** — 가장 낮음(안정적): 하이브 25.0% · 가장 높음: 씨제이이엔엠 150.0%" in lines[3]
    assert "유동비율** — 가장 높음: 씨제이이엔엠 120.0%" in lines[4] and "가장 낮음" not in lines[4]


def test_ranking():
    cs = [dart.analyze_company("K", {"code": c, "name": n}, 2025, "CFS", http=H)
          for c, n in (("00265324", "씨제이이엔엠"), ("01204056", "하이브"))]
    r = {x["key"]: x for x in dart.ranking(cs)}
    assert r["op_margin"]["best"] == ("하이브", 0.15) and r["op_margin"]["worst"][0] == "씨제이이엔엠"
    assert r["debt"]["best"][0] == "하이브"
    assert r["current"]["best"][0] == "씨제이이엔엠" and r["current"]["worst"] is None
