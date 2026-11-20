"""미국 SEC EDGAR 공시 데이터(XBRL companyfacts)에서 연간 재무 수치를 뽑는다.

- API 키는 필요 없지만, SEC 정책상 요청 헤더(User-Agent)에 이름과 연락처 이메일을 넣어야 한다.
- 결과는 dart.analyze_company 와 같은 모양의 dict 로 돌려줘서 화면 코드를 같이 쓴다.
데이터 출처: U.S. Securities and Exchange Commission, EDGAR (https://www.sec.gov/edgar)
"""
from __future__ import annotations

from datetime import date

import requests

import dart

TICKERS = "https://www.sec.gov/files/company_tickers.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/"
TIMEOUT = 60

# 계정별 후보 태그 (위에서부터 먼저 찾음). 회사·연도에 따라 쓰는 태그가 달라서 연도마다 따로 찾는다.
CONCEPTS = {
    "rev": [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"), ("us-gaap", "SalesRevenueNet"),
            ("us-gaap", "SalesRevenueGoodsNet"), ("ifrs-full", "Revenue")],
    "op": [("us-gaap", "OperatingIncomeLoss"), ("ifrs-full", "ProfitLossFromOperatingActivities")],
    "net": [("us-gaap", "ProfitLoss"), ("us-gaap", "NetIncomeLoss"), ("ifrs-full", "ProfitLoss")],
    "assets": [("us-gaap", "Assets"), ("ifrs-full", "Assets")],
    "liab": [("us-gaap", "Liabilities"), ("ifrs-full", "Liabilities")],
    "equity": [("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
               ("us-gaap", "StockholdersEquity"), ("ifrs-full", "Equity")],
    "ca": [("us-gaap", "AssetsCurrent"), ("ifrs-full", "CurrentAssets")],
    "cl": [("us-gaap", "LiabilitiesCurrent"), ("ifrs-full", "CurrentLiabilities")],
}
FLOW = {"rev", "op", "net"}  # 기간(1년) 수치. 나머지는 결산일 시점 잔액
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"}
TOTAL_LE = ("us-gaap", "LiabilitiesAndStockholdersEquity")


def _headers(ua: str) -> dict:
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def fetch_tickers(ua: str, http=requests) -> list[dict]:
    """SEC 티커 목록 → [{cik, ticker, title}] (회사당 하나, 이름순)."""
    res = http.get(TICKERS, headers=_headers(ua), timeout=TIMEOUT)
    res.raise_for_status()
    seen, out = set(), []
    for v in res.json().values():
        cik = int(v["cik_str"])
        if cik in seen:  # 같은 회사의 다른 주식(예: 의결권 다른 주식)은 첫 번째만
            continue
        seen.add(cik)
        out.append({"cik": cik, "ticker": str(v["ticker"]), "title": str(v["title"]).strip()})
    return sorted(out, key=lambda x: x["title"].lower())


def fetch_facts(ua: str, cik: int, http=requests) -> dict:
    res = http.get(FACTS.format(cik=cik), headers=_headers(ua), timeout=TIMEOUT)
    if res.status_code == 404:
        raise dart.DartError("404", "SEC에 이 회사의 재무 데이터(XBRL)가 없습니다.")
    res.raise_for_status()
    return res.json()


def _d(s: str) -> date:
    return date.fromisoformat(s)


def fiscal_label(end: date) -> int:
    """결산일 → 회계연도 표기. 1~3월 결산은 직전 연도로 본다 (예: 2026-01-31 결산 → 2025)."""
    return end.year if end.month >= 4 else end.year - 1


def _is_year(f: dict) -> bool:
    if not f.get("start"):
        return False
    days = (_d(f["end"]) - _d(f["start"])).days
    return 340 <= days <= 380


def _currency_units(units: dict) -> list[str]:
    return [u for u in units if len(u) == 3 and u.isalpha() and u.isupper()]


def detect_currency(facts: dict) -> str | None:
    for key in ("assets", "rev", "net"):
        for tax, name in CONCEPTS[key]:
            c = facts.get(tax, {}).get(name)
            if c:
                cur = _currency_units(c.get("units", {}))
                if cur:
                    return cur[0]
    return None


def _values(facts: dict, tax: str, name: str, cur: str) -> list[dict]:
    c = facts.get(tax, {}).get(name)
    if not c:
        return []
    return [f for f in c.get("units", {}).get(cur, []) if f.get("form") in ANNUAL_FORMS]


def fiscal_year_ends(facts: dict, cur: str) -> dict[int, date]:
    """연간 손익 수치의 기간 끝 날짜들로 회계연도별 결산일을 정한다."""
    ends: dict[int, date] = {}
    for key in ("rev", "net", "op"):
        for tax, name in CONCEPTS[key]:
            for f in _values(facts, tax, name, cur):
                if _is_year(f):
                    e = _d(f["end"])
                    y = fiscal_label(e)
                    if y not in ends or e > ends[y]:
                        ends[y] = e
    return ends


def _pick(cands: list[dict]) -> dict | None:
    """같은 기간 수치가 여러 보고서에 있으면 가장 최근에 제출된 것(정정 반영)을 쓴다."""
    return max(cands, key=lambda f: (f.get("filed", ""), f.get("accn", ""))) if cands else None


def value_for(facts: dict, key: str, end: date, cur: str):
    """(값, 태그이름, 접수번호) 또는 (None, None, None)"""
    for tax, name in CONCEPTS[key]:
        vals = _values(facts, tax, name, cur)
        if key in FLOW:
            cands = [f for f in vals if _is_year(f) and _d(f["end"]) == end]
        else:
            cands = [f for f in vals if not f.get("start") and _d(f["end"]) == end]
        hit = _pick(cands)
        if hit is not None:
            return float(hit["val"]), f"{tax}:{name}", hit.get("accn", "")
    return None, None, None


def analyze_company(ua: str, comp: dict, year: int, http=requests, facts_json: dict | None = None) -> dict:
    """comp = {cik, ticker, title}. year 회계연도를 포함한 최근 5개년."""
    data = facts_json if facts_json is not None else fetch_facts(ua, comp["cik"], http=http)
    facts = data.get("facts", {})
    cur = detect_currency(facts)
    if not cur:
        raise dart.DartError("013", "SEC 데이터에서 재무 수치를 찾지 못했습니다.")
    ends = fiscal_year_ends(facts, cur)
    if year not in ends:
        latest = max(ends) if ends else None
        raise dart.DartError("013", f"{year} 회계연도 연간 보고서 수치가 아직 없습니다"
                                    + (f" (최근: {latest} 회계연도)" if latest else ""))
    standard = "IFRS" if "ifrs-full" in facts and "us-gaap" not in facts else "US GAAP"

    years, ids, links, period_end = {}, {}, {}, {}
    for y in range(year - 4, year + 1):
        amt = {}
        e = ends.get(y)
        if e is not None:
            period_end[y] = e.isoformat()
            accn_y = ""
            for key in CONCEPTS:
                v, tag, accn = value_for(facts, key, e, cur)
                if v is not None:
                    amt[key] = v
                    ids.setdefault(key, {})[y] = tag
                    accn_y = accn_y or accn
            # 부채총계를 따로 공시하지 않는 회사: 부채와자본총계 − 자본총계
            if "liab" not in amt and "equity" in amt:
                tot = _pick([f for f in _values(facts, *TOTAL_LE, cur) if not f.get("start") and _d(f["end"]) == e])
                if tot is not None:
                    amt["liab"] = float(tot["val"]) - amt["equity"]
                    ids.setdefault("liab", {})[y] = "계산: 부채와자본총계 − 자본총계"
            if accn_y:
                links[y] = ARCHIVE.format(cik=comp["cik"], accn=accn_y.replace("-", ""))
        years[y] = amt

    yr = {y: {"amount": years[y], "ratio": dart.ratios(years[y], years.get(y - 1))} for y in sorted(years)}
    accounts = {}
    for m in dart.METRICS:
        k = m["key"]
        tags = ids.get(k, {})
        if tags:
            last = tags[max(tags)]
            accounts[k] = {"id": last, "nm": last.split(":")[-1]}
        else:
            accounts[k] = None
    missing = [dart.METRIC_LABEL[k] for k in CONCEPTS if accounts.get(k) is None]
    gaps = [y for y in range(year - 4, year + 1) if not years[y]]
    return {
        "name": data.get("entityName") or comp["title"], "code": str(comp["cik"]), "stock": comp["ticker"],
        "fs": "US", "year": year, "years": yr, "accounts": accounts, "missing": missing,
        "older_note": (", ".join(map(str, gaps)) + " 회계연도 수치 없음") if gaps else "",
        "fell_back": False, "market": "US", "currency": cur, "standard": standard,
        "period_end": period_end, "links": links, "src": {},
    }
