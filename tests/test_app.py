import sys
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fake_dart as F  # noqa: E402

APP = str(ROOT / "app.py")


UA = "Kim Jimin jimin@example.com"


def run_app(monkeypatch, key="K", ua=UA):
    monkeypatch.setattr(requests, "get", F.fake_get)
    at = AppTest.from_file(APP, default_timeout=60)
    if key is not None:
        at.secrets["DART_API_KEY"] = key
    if ua is not None:
        at.secrets["SEC_USER_AGENT"] = ua
    at.run()
    return at


def trend_radio(at):
    return next(r for r in at.radio if r.label == "지표 선택")


def md(at):
    return " ".join(m.value for m in at.markdown)


def test_no_key_us_still_works(monkeypatch):
    at = run_app(monkeypatch, key=None)
    assert not at.exception
    assert at.multiselect[0].disabled and not at.multiselect[1].disabled
    assert any("DART_API_KEY" in c.value for c in at.caption)
    at.multiselect[1].set_value(["MICRON TECHNOLOGY INC (MU)"])
    at.selectbox[0].set_value(2025)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert "2025 회계연도 재무 비교" in md(at) and "MICRON TECHNOLOGY INC / 1개사" in md(at)


def test_no_keys_at_all(monkeypatch):
    at = run_app(monkeypatch, key=None, ua=None)
    assert not at.exception
    assert at.multiselect[0].disabled and at.multiselect[1].disabled


def test_bad_key(monkeypatch):
    at = run_app(monkeypatch, key="BAD")
    assert not at.exception
    assert any("등록되지 않은 키" in c.value for c in at.caption)


def test_first_screen(monkeypatch):
    at = run_app(monkeypatch)
    assert not at.exception
    opts = at.multiselect[0].options
    assert "씨제이이엔엠 (035760)" in opts and not any("무신사" in o for o in opts)
    assert "<b>조회</b>를 누르세요" in md(at)
    assert at.button[0].label == "조회"


def test_empty_submit(monkeypatch):
    at = run_app(monkeypatch)
    at.button[0].click().run()
    assert not at.exception
    assert "1개 이상 선택" in md(at)


def test_full_report(monkeypatch):
    at = run_app(monkeypatch)
    at.multiselect[0].set_value(["씨제이이엔엠 (035760)", "하이브 (352820)", "제이와이피엔터테인먼트 (035900)"])
    at.selectbox[0].set_value(2025)
    at.button[0].click().run()
    assert not at.exception, at.exception
    t = md(at)
    assert "<b>제이와이피엔터테인먼트</b> 조회 제외" in t
    assert "2025 회계연도 재무 비교" in t and "씨제이이엔엠, 하이브 / 2개사" in t
    assert "개별 기준 적용" in t and "2021~2022년" in t and "미확인 계정: 유동자산, 유동부채" in t
    # 주요 지표: 매출 50,000억, 전년비 ▲ 11.1%, 영업이익률 4.0%, 부채비율 하락 ▼
    assert "<td>50,000</td>" in t and "▲ 11.1%" in t and "<td>4.0%</td>" in t and "▼ 6.8%p" in t
    # 지표 순위: 영업이익률 우수 하이브 15.0%, 미흡 CJ 4.0%
    assert "하이브 <b>15.0%</b>" in t and "씨제이이엔엠 <b>4.0%</b>" in t
    # 상세 비교표 강조
    assert '<td class="best">15.0%</td>' in t
    # 원본 데이터 링크
    assert "rcpNo=20260310000111" in t
    # 5개년 추이 지표 바꾸기
    trend_radio(at).set_value("부채비율").run()
    assert not at.exception
    assert "부채비율 추이" in md(at) and "2025 회계연도 재무 비교" in md(at)


def test_single_company(monkeypatch):
    at = run_app(monkeypatch)
    at.multiselect[0].set_value(["씨제이이엔엠 (035760)"])
    at.selectbox[0].set_value(2025)
    at.button[0].click().run()
    assert not at.exception, at.exception
    t = md(at)
    assert 'class="best"' not in t  # 1개사면 강조 없음
    assert '<td class="l flat">–</td>' in t  # 미흡 칸 비어 있음


def eok_str(v):
    return f"{v / 1e8:,.0f}"


def test_us_needs_user_agent(monkeypatch):
    at = run_app(monkeypatch, ua=None)
    assert not at.exception
    assert at.multiselect[1].disabled
    assert any("SEC_USER_AGENT" in c.value for c in at.caption)


def test_too_many(monkeypatch):
    at = run_app(monkeypatch)
    at.multiselect[0].set_value(at.multiselect[0].options[:5])
    at.multiselect[1].set_value(at.multiselect[1].options[:2])
    at.button[0].click().run()
    assert not at.exception
    assert "최대 6개까지" in md(at) and "현재 7개" in md(at)


def test_kr_us_currency(monkeypatch):
    at = run_app(monkeypatch)
    assert "MICRON TECHNOLOGY INC (MU)" in at.multiselect[1].options
    at.multiselect[0].set_value(["씨제이이엔엠 (035760)"])
    at.multiselect[1].set_value(["MICRON TECHNOLOGY INC (MU)", "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD (TSM)"])
    at.selectbox[0].set_value(2025)
    at.button[0].click().run()
    assert not at.exception, at.exception
    t = md(at)
    rate = round(F.usdkrw("2026-11-19"), 6)
    # 기본: 원화 + 현재 환율 → 마이크론 매출을 원화(억원)로
    assert f"<td>{eok_str(37.4e9 * rate)}</td>" in t
    assert "<td>50,000</td>" in t                        # CJ는 그대로
    assert "결산일 2025-08-28" in t and "US GAAP" in t and "회계 기준이 달라" in t
    assert f"1 USD = {rate:,.2f} KRW" in t and "2026-11-19" in t
    assert "TWD→KRW 금액은 표시하지 않았습니다" in t       # 대만 달러 환율 없음
    assert '<span class="mk">미국</span>' in t and "백만 달러" not in t
    # 비율은 통화와 무관: 마이크론 영업이익률
    assert f"{9.8 / 37.4 * 100:.1f}%" in t

    # 달러 표기 → CJ 매출을 달러(백만 달러)로
    at.radio(key="show_cur").set_value("달러로 표기").run()
    assert not at.exception, at.exception
    t = md(at)
    assert f"<td>{5e12 * round(1 / F.usdkrw('2026-11-19'), 6) / 1e6:,.0f}</td>" in t
    assert "<td>37,400</td>" in t and "백만 달러" in t      # 마이크론은 그대로 (백만 달러)
    inv = 1 / round(1 / F.usdkrw("2026-11-19"), 6)
    assert f"1 USD = {inv:,.2f} KRW" in t

    # 연도별 환율 → 원화 표기에서 마이크론 2025 매출은 FY 기간 평균
    at.radio(key="show_cur").set_value("원화로 표기")
    at.radio(key="rate_mode").set_value("연도별 환율").run()
    assert not at.exception, at.exception
    days = [d for d in F.fx_series_dates("2024-08-29", "2025-08-28")]
    avg = sum(F.usdkrw(d) for d in days) / len(days)
    t = md(at)
    assert f"<td>{eok_str(37.4e9 * avg)}</td>" in t
    assert "연도별 환율 적용" in t
    # 자산은 결산일(2025-08-28, 목) 환율
    assert f"<td>{eok_str(82.8e9 * F.usdkrw('2025-08-28'))}</td>" in t


def test_dart_blocked_key_hidden_us_works(monkeypatch):
    at = run_app(monkeypatch, key="DOWN")
    assert not at.exception
    caps = " ".join(c.value for c in at.caption)
    assert "해외 서버" in caps and "crtfc_key" not in caps and "DOWN" not in caps
    assert at.multiselect[0].disabled and not at.multiselect[1].disabled
