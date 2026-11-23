import gzip
import json
import sys
from datetime import date
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
import prices  # noqa: E402
import quarter  # noqa: E402

H = F.FakeHttp
CJ = {"code": "00265324", "name": "씨제이이엔엠", "stock": "035760"}
T = 1e12


def annual_years():
    a = dart.analyze_company("K", CJ, 2025, "CFS", http=H)
    return dart.cache_entry(a)["years"]


def test_labels_and_latest():
    assert quarter.shift("2026Q1", -1) == "2025Q4" and quarter.shift("2025Q4", 1) == "2026Q1"
    assert quarter.last_n("2026Q3", 4) == ["2025Q4", "2026Q1", "2026Q2", "2026Q3"]
    assert quarter.latest_quarter(date(2026, 11, 20)) == "2026Q3"
    assert quarter.latest_quarter(date(2026, 11, 10)) == "2026Q2"
    assert quarter.latest_quarter(date(2026, 4, 10)) == "2025Q4"
    assert quarter.latest_quarter(date(2026, 2, 1)) == "2025Q3"


def test_kr_quarters_with_annual_cache():
    ay = annual_years()
    F.CALLS.clear()
    e = quarter.kr_quarters("K", CJ, "2026Q3", annual_years=ay, http=H)
    q = e["q"]
    assert q["2026Q3"]["rev"] == pytest.approx(1.5 * T) and q["2026Q1"]["rev"] == pytest.approx(1.25 * T)
    assert q["2025Q1"]["rev"] == pytest.approx(1.1 * T)          # 1분기 보고서의 누적 칸 빈 경우 처리
    assert q["2025Q4"]["rev"] == pytest.approx((5.0 - 3.6) * T)  # 4분기 = 연간 − 3분기 누적
    assert q["2025Q4"]["op"] == pytest.approx((0.2 - 0.12) * T)
    assert "2025Q4" in e["derived"] and "2024Q4" in e["derived"]
    assert q["2024Q4"]["rev"] == pytest.approx((4.5 - 3.15) * T)   # 전년 3분기 보고서로 계산한 전전년 4분기
    assert q["2026Q2"]["assets"] == pytest.approx(10.4 * T) and q["2025Q4"]["equity"] == pytest.approx(4 * T)
    # 연간 데이터가 있으니 사업보고서는 다시 요청하지 않음
    assert all(p.get("reprt_code") != "11011" for _, p in F.CALLS if "fnlttSinglAcntAll" in _)
    t = quarter.ttm(e)
    assert t["amount"]["rev"] == pytest.approx((1.4 + 1.25 + 1.35 + 1.5) * T)
    assert t["ratio"]["roe"] == pytest.approx((0.03 + 0.04 + 0.04 + 0.05) / 4.3)
    assert t["ratio"]["growth"] == pytest.approx(5.5 / (1.35 + 1.1 + 1.2 + 1.3) - 1)  # 직전 4개 분기 대비
    assert quarter.yoy(e, "2026Q3", "rev") == pytest.approx(1.5 / 1.3 - 1)
    assert quarter.margin(e, "2026Q3") == pytest.approx(0.09 / 1.5)


def test_kr_quarters_without_annual_fetches_annual():
    F.CALLS.clear()
    e = quarter.kr_quarters("K", CJ, "2026Q3", http=H)
    assert any(p.get("reprt_code") == "11011" and p.get("bsns_year") == "2025" for _, p in F.CALLS)
    assert e["q"]["2025Q4"]["rev"] == pytest.approx(1.4 * T)


def test_kr_quarters_no_data():
    with pytest.raises(dart.DartError):
        quarter.kr_quarters("K", {"code": "01204056", "name": "하이브"}, "2026Q3", http=H)


def test_us_quarters_micron():
    e = quarter.us_quarters(F.MU_FACTS)
    q = e["q"]
    assert e["latest"] == "2025Q3"
    assert sorted(q) == ["2023Q4", "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3"]
    assert q["2023Q4"]["rev"] == pytest.approx(4.7e9)              # 9~11월 분기 → 달력 4분기
    assert q["2024Q3"]["rev"] == pytest.approx((25.1 - 17.3) * 1e9)  # 계산한 회계 4분기
    assert "2024Q3" in e["derived"]
    assert q["2025Q3"]["rev"] == pytest.approx(11.3e9)  # 10-K의 3개월 값 우선 (9개월 차감값 아님)
    assert "2025Q3" in e["derived"]  # 영업이익은 3개월 값이 없어 계산값
    assert q["2025Q3"]["op"] == pytest.approx((9.8 - 6.0) * 1e9)
    assert q["2025Q2"]["assets"] == pytest.approx(78e9) and q["2025Q3"]["assets"] == pytest.approx(82.8e9)
    assert q["2025Q2"]["liab"] == pytest.approx(78e9 - 50e9)  # 부채총계 없음 → 부채와자본총계 − 자본
    assert e["period_end"]["2025Q3"] == "2025-08-28"
    t = quarter.ttm(e)
    assert t["amount"]["rev"] == pytest.approx(37.4e9)
    assert t["ratio"]["growth"] == pytest.approx(37.4 / 25.1 - 1)   # 직전 4개 분기 = FY2024 와 같음


def test_kr_prices_paging_and_filter():
    rows = prices.kr_prices("KEY", "005930", date(2022, 1, 1), date(2026, 11, 19), http=H)
    assert len(rows) > 1000  # 여러 페이지
    assert all(r["date"] != "2026-01-02" or r["close"] != 1 for r in rows)  # 다른 종목 제외
    assert rows == sorted(rows, key=lambda r: r["date"])
    with pytest.raises(prices.PriceError) as ex:
        prices.kr_prices("BADKR", "005930", date(2026, 1, 1), date(2026, 2, 1), http=H)
    assert "인증키" in str(ex.value)
    # 끝날 포함 (endBasDt 는 '미만' 조건이라 하루 뒤로 요청)
    rows = prices.kr_prices("KEY", "005930", date(2026, 11, 16), date(2026, 11, 20), http=H)
    assert rows[-1]["date"] >= "2026-11-20"


def test_us_prices():
    rows = prices.us_prices("KEY", "MU", date(2026, 1, 1), date(2026, 3, 1), http=H)
    assert rows[0]["date"] < rows[-1]["date"] and rows[0]["close"] == 100
    assert prices.period_return(rows) == pytest.approx(rows[-1]["close"] / 100 - 1)
    with pytest.raises(prices.PriceError) as ex:
        prices.us_prices("LIMIT", "MU", date(2026, 1, 1), date(2026, 3, 1), http=H)
    assert "한도" in str(ex.value)


def test_collector_quarterly_phase(tmp_path):
    annual = collect_kr.collect("K", 2025, http=H, out=str(tmp_path / "a.gz"), part=str(tmp_path / "a.json"),
                                pause=0, log=lambda *a: None)
    qd = collect_kr.collect_quarterly("K", "2026Q3", annual, http=H, out=str(tmp_path / "q.gz"),
                                      part=str(tmp_path / "q.json"), pause=0, log=lambda *a: None)
    assert qd["latest"] == "2026Q3"
    assert qd["companies"]["00265324"]["status"] == "ok"
    assert qd["companies"]["01204056"]["status"] == "nodata"
    assert "00258689" not in qd["companies"]  # 연간 데이터 없는 회사는 분기도 건너뜀
    with gzip.open(tmp_path / "q.gz", "rt", encoding="utf-8") as f:
        assert json.load(f)["companies"]["00265324"]["q"]["2025Q4"]["rev"] == pytest.approx(1.4 * T)


def test_app_quarter_position_price_tabs(tmp_path, monkeypatch):
    annual = collect_kr.collect("K", 2025, http=H, out=str(tmp_path / "data" / "kr_financials.json.gz"),
                                part=str(tmp_path / "p1.json"), pause=0, log=lambda *a: None)
    collect_kr.collect_quarterly("K", "2026Q3", annual, http=H, out=str(tmp_path / "data" / "kr_quarterly.json.gz"),
                                 part=str(tmp_path / "p2.json"), pause=0, log=lambda *a: None)
    monkeypatch.setattr(requests, "get", F.fake_get)
    monkeypatch.setenv("PEERSCOPE_KR_CACHE", str(tmp_path / "data" / "kr_financials.json.gz"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.secrets["SEC_USER_AGENT"] = "Kim Jimin jimin@example.com"
    at.secrets["DATA_GO_KR_KEY"] = "KRKEY"
    at.run()
    assert any("분기는 2026년 3분기까지" in c.value for c in at.caption)
    at.multiselect[0].set_value(["씨제이이엔엠 (035760)", "하이브 (352820)"])
    at.multiselect[1].set_value(["MICRON TECHNOLOGY INC (MU)"])
    at.selectbox[0].set_value(2025)
    at.button[0].click().run()
    assert not at.exception, at.exception
    t = " ".join(m.value for m in at.markdown)
    # 분기 실적: CJ 2026 3Q 매출 1.5조 = 15,000억, 전년 동기비 ▲ 15.4%
    assert "<td>2026 3Q</td>" in t and "<td>15,000</td>" in t and "▲ 15.4%" in t
    # 마이크론 최근 분기(2025 3Q) 매출 11.3B → 원화
    rate = round(F.usdkrw("2026-11-19"), 6)
    assert f"<td>{11.3e9 * rate / 1e8:,.0f}</td>" in t
    # TTM: CJ 55,000억 (직전 4개 분기 대비 ▲ 11.1%), 마이크론 성장률 ▲ 49.0%
    assert "<td>55,000</td>" in t and "▲ 49.0%" in t and "▲ 11.1%" in t
    caps = " ".join(c.value for c in at.caption)
    assert "4분기(2024 3Q, 2024 4Q, 2025 3Q, 2025 4Q)는 연간 실적에서" in caps
    assert "분기 데이터 없음: 하이브" in " ".join(c.value for c in at.caption)
    # 주가: 국내는 키 있음 → 표, 미국은 키 없음 → 안내
    assert "Twelve Data 키(TWELVE_DATA_KEY)를 설정하면" in t and "1년 수익률" in t
    assert any(s_.label == "회사 선택" for s_ in at.selectbox)
    # 분기 지표·주가 기간 바꾸기
    at.radio(key="qpick").set_value("영업이익률").run()
    at.radio(key="px_span").set_value("3년").run()
    assert not at.exception, at.exception
    # 원화 → 달러
    at.radio(key="show_cur").set_value("달러로 표기").run()
    assert not at.exception, at.exception
    assert "<td>11,300</td>" in " ".join(m.value for m in at.markdown)  # 마이크론 분기 매출 (백만 달러)


def test_price_tab_hidden_without_keys(monkeypatch, tmp_path):
    F.CALLS.clear()
    monkeypatch.setattr(requests, "get", F.fake_get)
    monkeypatch.setenv("PEERSCOPE_KR_CACHE", "/nonexistent/kr.json.gz")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.secrets["SEC_USER_AGENT"] = "Kim Jimin jimin@example.com"
    at.run()
    at.multiselect[1].set_value(["MICRON TECHNOLOGY INC (MU)"])
    at.selectbox[0].set_value(2025)
    at.button[0].click().run()
    assert not at.exception, at.exception
    t = " ".join(m.value for m in at.markdown)
    assert "개인 PC에서 실행할 때만" in t
    assert not any(r.key == "px_span" for r in at.radio)
    assert not any("twelvedata" in u or "apis.data.go.kr" in u for u, _ in F.CALLS)


def test_run_local_writes_keys_outside_project(tmp_path):
    import run_local
    path = tmp_path / ".streamlit" / "secrets.toml"
    answers = iter(['"abc"', "", 'Jimin "J" Kim a@b.com'])
    run_local.write_keys(ask=lambda _: next(answers), path=str(path))
    import tomllib
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data == {"DATA_GO_KR_KEY": "abc", "SEC_USER_AGENT": 'Jimin "J" Kim a@b.com'}


def test_app_ttm_mode(tmp_path, monkeypatch):
    annual = collect_kr.collect("K", 2025, http=H, out=str(tmp_path / "data" / "kr_financials.json.gz"),
                                part=str(tmp_path / "p1.json"), pause=0, log=lambda *a: None)
    collect_kr.collect_quarterly("K", "2026Q3", annual, http=H, out=str(tmp_path / "data" / "kr_quarterly.json.gz"),
                                 part=str(tmp_path / "p2.json"), pause=0, log=lambda *a: None)
    monkeypatch.setattr(requests, "get", F.fake_get)
    monkeypatch.setenv("PEERSCOPE_KR_CACHE", str(tmp_path / "data" / "kr_financials.json.gz"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.secrets["SEC_USER_AGENT"] = "Kim Jimin jimin@example.com"
    at.run()
    assert at.selectbox[0].value == "TTM"  # 기본값이 최근 4개 분기
    at.multiselect[0].set_value(["씨제이이엔엠 (035760)", "하이브 (352820)"])
    at.multiselect[1].set_value(["MICRON TECHNOLOGY INC (MU)"])
    at.button[0].click().run()
    assert not at.exception, at.exception
    t = " ".join(m.value for m in at.markdown)
    assert "최근 4개 분기 재무 비교 (회사별 가장 최근 4개 분기)" in t
    assert "직전 4개 분기 대비" in t
    # 주요 지표: CJ TTM 매출 55,000억, 직전 4개 분기 대비 ▲ 11.1%, 영업이익률 3,000/55,000 = 5.5%
    assert "<td>55,000</td>" in t and "▲ 11.1%" in t and "<td>5.5%</td>" in t
    assert "<b>하이브</b> 최근 4개 분기 데이터가 없어 이 보기에서 제외" in t
    assert "기간 2025 4Q~2026 3Q" in t and "기간 2024 4Q~2025 3Q" in t
    # 5개년 추이는 연간 데이터 그대로 (하이브 포함)
    assert any("연간 실적(사업보고서) 기준" in c.value for c in at.caption)
    rate = round(F.usdkrw("2026-11-19"), 6)
    assert f"<td>{37.4e9 * rate / 1e8:,.0f}</td>" in t  # 마이크론 TTM 매출 (= FY2025)
    at.radio(key="rate_mode").set_value("연도별 환율").run()
    assert not at.exception, at.exception
