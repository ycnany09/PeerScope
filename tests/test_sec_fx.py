import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import dart  # noqa: E402
import fake_dart as F  # noqa: E402
import fx  # noqa: E402
import sec  # noqa: E402

H = F.FakeHttp
UA = "Kim Jimin jimin@example.com"
MU = {"cik": 723125, "ticker": "MU", "title": "MICRON TECHNOLOGY INC"}


def test_tickers_dedup_sorted():
    t = sec.fetch_tickers(UA, http=H)
    assert [x["ticker"] for x in t].count("GOOG") == 0 and len(t) == 4
    assert [x["title"].lower() for x in t] == sorted(x["title"].lower() for x in t)


def test_user_agent_required():
    with pytest.raises(Exception):
        sec.fetch_tickers("no-email", http=H)


def test_fiscal_label():
    from datetime import date
    assert sec.fiscal_label(date(2025, 8, 28)) == 2025
    assert sec.fiscal_label(date(2026, 1, 31)) == 2025
    assert sec.fiscal_label(date(2025, 12, 31)) == 2025


def test_micron_five_years():
    c = sec.analyze_company(UA, MU, 2025, http=H)
    assert c["market"] == "US" and c["currency"] == "USD" and c["standard"] == "US GAAP"
    assert sorted(c["years"]) == [2021, 2022, 2023, 2024, 2025]
    rev = {y: c["years"][y]["amount"]["rev"] for y in c["years"]}
    assert rev[2021] == pytest.approx(27.7e9)          # 예전 태그
    assert rev[2023] == pytest.approx(15.54e9)         # 정정된 최신 값
    assert rev[2025] == pytest.approx(37.4e9)          # 4분기 3개월치(11.3B)·10-Q 무시
    a25 = c["years"][2025]["amount"]
    assert a25["liab"] == pytest.approx(82.8e9 - 54.2e9)  # 부채총계 = 부채와자본총계 − 자본
    assert c["period_end"][2025] == "2025-08-28"
    assert c["accounts"]["rev"]["id"] == "us-gaap:Revenues"
    assert c["accounts"]["liab"]["id"].startswith("계산")
    assert c["links"][2025].startswith("https://www.sec.gov/Archives/edgar/data/723125/")
    r = c["years"][2025]["ratio"]
    assert r["op_margin"] == pytest.approx(9.8 / 37.4)
    assert r["growth"] == pytest.approx((37.4 - 25.1) / 25.1)
    assert c["years"][2024]["ratio"]["growth"] == pytest.approx((25.1 - 15.54) / 15.54)
    assert c["missing"] == []


def test_missing_year():
    with pytest.raises(dart.DartError) as e:
        sec.analyze_company(UA, MU, 2026, http=H)
    assert "2026 회계연도" in e.value.message and "최근: 2025" in e.value.message


def test_ifrs_twd():
    c = sec.analyze_company(UA, {"cik": 1046179, "ticker": "TSM", "title": "TSMC"}, 2025, http=H)
    assert c["currency"] == "TWD" and c["standard"] == "IFRS"
    assert c["years"][2025]["amount"]["rev"] == 6e12
    assert "영업이익" in c["missing"]


def test_no_facts():
    with pytest.raises(dart.DartError):
        sec.analyze_company(UA, {"cik": 999, "ticker": "OLD", "title": "OLD"}, 2025, http=H)


def test_fx_latest_and_series():
    r, d = fx.latest("USD", "KRW", http=H)
    assert d == "2026-11-19" and r == pytest.approx(F.usdkrw("2026-11-19"), rel=1e-6)
    assert fx.latest("KRW", "KRW", http=H)[0] == 1.0
    with pytest.raises(fx.FxError):
        fx.latest("TWD", "KRW", http=H)
    ser = fx.series("USD", "KRW", "2024-01-01", "2025-12-31", http=H)
    avg = fx.period_average(ser, "2025-12-31")
    vals = [F.usdkrw(d) for d in F.fx_series_dates("2025-01-01", "2025-12-31")]
    assert avg == pytest.approx(sum(vals) / len(vals))
    # 2025-08-30(토) 결산 → 직전 금요일 환율
    assert fx.on_date(ser, "2025-08-30") == pytest.approx(F.usdkrw("2025-08-29"))
    assert fx.on_date(ser, "2023-01-01") is None
    assert fx.on_date([("2025-01-01", 1.0)], "2025-02-01") is None  # 7일 넘게 빔


def test_us_korean_labels():
    import us_names
    assert us_names.label("NVIDIA CORP", "NVDA") == "엔비디아 · NVIDIA CORP (NVDA)"
    assert us_names.label("COCA COLA CO", "KO") == "코카콜라 · COCA COLA CO (KO)"
    assert us_names.label("Apple Inc.", "AAPL").startswith("애플 · ")
    assert "구글" in us_names.label("Alphabet Inc.", "GOOGL")
    assert us_names.label("SOME SMALL CO", "ZZZZ") == "SOME SMALL CO (ZZZZ)"  # 목록에 없으면 영문 그대로
    # 같은 한글 이름이 서로 다른 회사에 붙지 않았는지 (알파벳·버크셔 주식 종류는 같은 회사라 예외)
    from collections import Counter
    dup = {k: n for k, n in Counter(us_names.KO.values()).items() if n > 1}
    assert set(dup) <= {"알파벳(구글)", "버크셔 해서웨이"}
