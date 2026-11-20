"""환율: Frankfurter API (유럽중앙은행 ECB 기준환율, 키 불필요).

- 현재 환율: 가장 최근 영업일 기준환율
- 연도별 환율: 손익 항목(매출·이익)은 그 회계연도 1년 평균, 재무상태 항목(자산·부채·자본)은 결산일 환율
데이터 출처: https://frankfurter.dev (ECB reference rates)
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

API = "https://api.frankfurter.dev/v1/"
TIMEOUT = 20


class FxError(Exception):
    pass


def latest(base: str, quote: str, http=requests) -> tuple[float, str]:
    """1 base = ? quote. (환율, 기준일)"""
    if base == quote:
        return 1.0, date.today().isoformat()
    res = http.get(API + "latest", params={"base": base, "symbols": quote}, timeout=TIMEOUT)
    try:
        j = res.json()
        return float(j["rates"][quote]), str(j.get("date", ""))
    except Exception as ex:
        raise FxError(f"{base}→{quote} 환율을 받지 못했습니다") from ex


def series(base: str, quote: str, start: str, end: str, http=requests) -> list[tuple[str, float]]:
    """기간 환율 [(날짜, 환율)] 날짜순."""
    if base == quote:
        return [(start, 1.0), (end, 1.0)]
    res = http.get(f"{API}{start}..{end}", params={"base": base, "symbols": quote}, timeout=TIMEOUT)
    try:
        rates = res.json()["rates"]
        out = sorted((d, float(v[quote])) for d, v in rates.items() if quote in v)
    except Exception as ex:
        raise FxError(f"{base}→{quote} 기간 환율을 받지 못했습니다") from ex
    if not out:
        raise FxError(f"{base}→{quote} 기간 환율이 비어 있습니다")
    return out


def period_average(ser: list[tuple[str, float]], end: str) -> float | None:
    """결산일까지 1년(365일) 평균."""
    e = date.fromisoformat(end)
    s = (e - timedelta(days=364)).isoformat()
    vals = [v for d, v in ser if s <= d <= end]
    return sum(vals) / len(vals) if vals else None


def on_date(ser: list[tuple[str, float]], end: str) -> float | None:
    """결산일 당일, 없으면(휴일) 그 직전 영업일 환율. 7일 넘게 비면 None."""
    e = date.fromisoformat(end)
    prior = [(d, v) for d, v in ser if d <= end]
    if not prior:
        return None
    d, v = prior[-1]
    return v if (e - date.fromisoformat(d)).days <= 7 else None
