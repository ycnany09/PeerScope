"""테스트용 가짜 DART 서버 응답."""
import io
import json
import zipfile

XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><corp_eng_name>SAMSUNG ELECTRONICS CO,.LTD</corp_eng_name><stock_code>005930</stock_code><modify_date>20250101</modify_date></list>
  <list><corp_code>00265324</corp_code><corp_name>씨제이이엔엠</corp_name><corp_eng_name>CJ ENM CO., Ltd.</corp_eng_name><stock_code>035760</stock_code><modify_date>20250101</modify_date></list>
  <list><corp_code>01204056</corp_code><corp_name>하이브</corp_name><corp_eng_name>HYBE Co.,Ltd.</corp_eng_name><stock_code>352820</stock_code><modify_date>20250101</modify_date></list>
  <list><corp_code>00258689</corp_code><corp_name>제이와이피엔터테인먼트</corp_name><corp_eng_name/><stock_code>035900</stock_code><modify_date>20250101</modify_date></list>
  <list><corp_code>08888888</corp_code><corp_name>무신사</corp_name><corp_eng_name>MUSINSA</corp_eng_name><stock_code> </stock_code><modify_date>20250101</modify_date></list>
  <list><corp_code>07777777</corp_code><corp_name>A&amp;B컴퍼니</corp_name><corp_eng_name></corp_eng_name><stock_code>123456</stock_code><modify_date>20250101</modify_date></list>
</result>"""


def row(sj, i, nm, a, b, c, rc="20260310000111"):
    return {"rcept_no": rc, "sj_div": sj, "account_id": i, "account_nm": nm,
            "thstrm_amount": a, "frmtrm_amount": b, "bfefrmtrm_amount": c}


def cj(rc, vals):
    """vals: 계정별 (당기, 전기, 전전기) 조원 단위"""
    T = 1_000_000_000_000
    f = lambda x: f"{int(x * T):,}"
    return [row("BS", "ifrs-full_CurrentAssets", "유동자산", *map(f, vals["ca"]), rc=rc),
            row("BS", "ifrs-full_Assets", "자산총계", *map(f, vals["assets"]), rc=rc),
            row("BS", "ifrs-full_CurrentLiabilities", "유동부채", *map(f, vals["cl"]), rc=rc),
            row("BS", "ifrs-full_Liabilities", "부채총계", *map(f, vals["liab"]), rc=rc),
            row("BS", "ifrs-full_Equity", "자본총계", *map(f, vals["equity"]), rc=rc),
            row("CIS", "ifrs-full_Revenue", "매출액", *map(f, vals["rev"]), rc=rc),
            row("CIS", "dart_OperatingIncomeLoss", "영업이익(손실)", *map(f, vals["op"]), rc=rc),
            row("CIS", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업 소유주지분", "1", "1", "1", rc=rc),
            row("CIS", "ifrs-full_ProfitLoss", "당기순이익(손실)", *map(f, vals["net"]), rc=rc)]


FIN = {
    # CJ ENM 2025 보고서: 2025·2024·2023 / 2023 보고서: 2023·2022·2021
    ("00265324", "2025", "CFS"): {"status": "000", "list": cj("20260310000111", {
        "ca": (3, 2.8, 2.6), "assets": (10, 9.5, 9), "cl": (2.5, 2.4, 2.3), "liab": (6, 5.8, 5.5),
        "equity": (4, 3.7, 3.5), "rev": (5, 4.5, 4), "op": (0.2, -0.05, 0.1), "net": (0.1, -0.12, 0.05)})},
    ("00265324", "2023", "CFS"): {"status": "000", "list": cj("20240315000222", {
        "ca": (2.6, 2.5, 2.4), "assets": (9, 8.5, 8), "cl": (2.3, 2.2, 2.1), "liab": (5.5, 5.2, 5),
        "equity": (3.5, 3.3, 3), "rev": (3.9, 3.5, 3.0), "op": (0.1, 0.13, 0.2), "net": (0.05, 0.1, 0.15)})},
    # 하이브: 연결 없음 → 개별, 이름으로 찾기, 2023 보고서 없음
    ("01204056", "2025", "CFS"): {"status": "013", "message": "조회된 데이타가 없습니다."},
    ("01204056", "2025", "OFS"): {"status": "000", "list": [
        row("BS", "-표준계정코드 미사용-", "자산총계", "5000000000000", "4000000000000", "3500000000000"),
        row("BS", "-표준계정코드 미사용-", "부채총계", "1000000000000", "900000000000", "800000000000"),
        row("BS", "-표준계정코드 미사용-", "자본총계", "4000000000000", "3100000000000", "2700000000000"),
        row("IS", "-표준계정코드 미사용-", "Ⅰ. 수익(매출액)", "2000000000000", "1800000000000", "1500000000000"),
        row("IS", "-표준계정코드 미사용-", "영업이익", "300000000000", "250000000000", "200000000000"),
        row("IS", "-표준계정코드 미사용-", "당기순이익", "250000000000", "200000000000", "150000000000")]},
    ("01204056", "2023", "OFS"): {"status": "013", "message": "조회된 데이타가 없습니다."},
    # JYP: 데이터 없음
    ("00258689", "2025", "CFS"): {"status": "013", "message": "조회된 데이타가 없습니다."},
    ("00258689", "2025", "OFS"): {"status": "013", "message": "조회된 데이타가 없습니다."},
}


class Resp:
    def __init__(self, content=b"", js=None, code=200):
        self.content, self._js, self.status_code = content, js, code

    def json(self):
        if self._js is None:
            raise ValueError("not json")
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def zipped(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml.encode("utf-8"))
    return buf.getvalue()


CALLS = []


def fake_get(url, params=None, timeout=None):
    CALLS.append((url, dict(params or {})))
    if url.endswith("corpCode.xml"):
        if params.get("crtfc_key") == "BAD":
            return Resp(b"<result><status>010</status><message>\xeb\x93\xb1\xeb\xa1\x9d\xeb\x90\x98\xec\xa7\x80 \xec\x95\x8a\xec\x9d\x80 \xed\x82\xa4\xec\x9e\x85\xeb\x8b\x88\xeb\x8b\xa4.</message></result>")
        return Resp(zipped(XML))
    k = (params["corp_code"], params["bsns_year"], params["fs_div"])
    return Resp(js=FIN.get(k, {"status": "013", "message": "조회된 데이타가 없습니다."}))


class FakeHttp:
    get = staticmethod(fake_get)


# ───────────── 가짜 SEC ─────────────
from datetime import date as _date, timedelta as _td

SEC_TICKERS = {
    "0": {"cik_str": 723125, "ticker": "MU", "title": "MICRON TECHNOLOGY INC"},
    "1": {"cik_str": 1046179, "ticker": "TSM", "title": "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD"},
    "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    "3": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    "4": {"cik_str": 999, "ticker": "OLD", "title": "OLD CO"},
}
MU_ENDS = ["2021-09-02", "2022-09-01", "2023-08-31", "2024-08-29", "2025-08-28"]
MU_STARTS = ["2020-09-04", "2021-09-03", "2022-09-02", "2023-09-01", "2024-08-30"]
B = 1e9


def _flow(vals, idx, form="10-K", filed=None, accn=None):
    out = []
    for i in idx:
        out.append({"start": MU_STARTS[i], "end": MU_ENDS[i], "val": vals[i], "fy": 2021 + i, "fp": "FY", "form": form,
                    "filed": filed or f"{2021 + i}-10-0{(i % 8) + 1}", "accn": accn or f"0000723125-{21 + i}-000010"})
    return out


def _inst(vals, idx):
    return [{"end": MU_ENDS[i], "val": vals[i], "fy": 2021 + i, "fp": "FY", "form": "10-K",
             "filed": f"{2021 + i}-10-05", "accn": f"0000723125-{21 + i}-000010"} for i in idx]


MU_REV = [27.7 * B, 30.8 * B, 15.5 * B, 25.1 * B, 37.4 * B]
MU_FACTS = {"entityName": "MICRON TECHNOLOGY INC", "facts": {"us-gaap": {
    # 2021~2022는 RevenueFromContract..., 2023~2025는 Revenues 태그 사용
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": _flow(MU_REV, [0, 1])}},
    "Revenues": {"units": {"USD": _flow(MU_REV, [2, 3, 4])
                           # 2023 매출을 2025년 보고서에서 15.54B로 정정 → 이 값을 써야 함
                           + [{"start": MU_STARTS[2], "end": MU_ENDS[2], "val": 15.54 * B, "fy": 2025, "fp": "FY",
                               "form": "10-K", "filed": "2025-10-03", "accn": "0000723125-25-000099"},
                              # 4분기(3개월) 수치는 연간이 아니므로 무시해야 함
                              {"start": "2025-05-30", "end": MU_ENDS[4], "val": 11.3 * B, "fy": 2025, "fp": "FY",
                               "form": "10-K", "filed": "2025-10-03", "accn": "0000723125-25-000099"},
                              # 10-Q 수치도 무시
                              {"start": MU_STARTS[4], "end": "2025-05-29", "val": 26.0 * B, "fy": 2025, "fp": "Q3",
                               "form": "10-Q", "filed": "2025-06-27", "accn": "0000723125-25-000050"}]}},
    "OperatingIncomeLoss": {"units": {"USD": _flow([8.7 * B, 9.7 * B, -5.7 * B, 1.3 * B, 9.8 * B], range(5))}},
    "NetIncomeLoss": {"units": {"USD": _flow([5.9 * B, 8.7 * B, -5.8 * B, 0.8 * B, 8.5 * B], range(5))}},
    "Assets": {"units": {"USD": _inst([58.8 * B, 66.3 * B, 64.3 * B, 69.4 * B, 82.8 * B], range(5))}},
    "LiabilitiesAndStockholdersEquity": {"units": {"USD": _inst([58.8 * B, 66.3 * B, 64.3 * B, 69.4 * B, 82.8 * B], range(5))}},
    "StockholdersEquity": {"units": {"USD": _inst([44.0 * B, 49.9 * B, 44.1 * B, 45.1 * B, 54.2 * B], range(5))}},
    "AssetsCurrent": {"units": {"USD": _inst([21.0 * B, 21.3 * B, 21.2 * B, 24.4 * B, 30.0 * B], range(5))}},
    "LiabilitiesCurrent": {"units": {"USD": _inst([4.8 * B, 5.3 * B, 4.9 * B, 9.2 * B, 11.2 * B], range(5))}},
}, "dei": {}}}

TSM_FACTS = {"entityName": "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD", "facts": {"ifrs-full": {
    "Revenue": {"units": {"TWD": [{"start": f"{y}-01-01", "end": f"{y}-12-31", "val": (2 + y - 2021) * 1e12, "fy": y,
                                   "fp": "FY", "form": "20-F", "filed": f"{y + 1}-04-15", "accn": f"0001046179-{y - 1999}-000001"}
                                  for y in range(2021, 2026)]}},
    "Assets": {"units": {"TWD": [{"end": f"{y}-12-31", "val": 5e12, "fy": y, "fp": "FY", "form": "20-F",
                                  "filed": f"{y + 1}-04-15", "accn": f"0001046179-{y - 1999}-000001"} for y in range(2021, 2026)]}},
}}}

# ───────────── 가짜 환율 (Frankfurter) ─────────────


def usdkrw(d: str) -> float:
    return 1100 + (_date.fromisoformat(d) - _date(2020, 1, 1)).days * 0.2


def fx_series_dates(start, end):
    d, e = _date.fromisoformat(start), _date.fromisoformat(end)
    out = []
    while d <= e:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += _td(days=1)
    return out


def fx_response(url, params):
    base, sym = params.get("base"), params.get("symbols")
    pair = {("USD", "KRW"): lambda d: usdkrw(d), ("KRW", "USD"): lambda d: 1 / usdkrw(d)}
    if (base, sym) not in pair:
        return Resp(js={"message": "not found"}, code=404)
    f = pair[(base, sym)]
    if url.endswith("/latest"):
        return Resp(js={"amount": 1.0, "base": base, "date": "2026-11-19", "rates": {sym: round(f("2026-11-19"), 6)}})
    rng = url.rsplit("/", 1)[1]
    s, e = rng.split("..")
    return Resp(js={"amount": 1.0, "base": base, "start_date": s, "end_date": e,
                    "rates": {d: {sym: f(d)} for d in fx_series_dates(s, e)}})


_old_fake_get = fake_get


def fake_get(url, params=None, timeout=None, headers=None):  # noqa: F811
    if "sec.gov" in url:
        CALLS.append((url, {"headers": headers}))
        if not headers or "@" not in headers.get("User-Agent", ""):
            return Resp(js={}, code=403)
        if url.endswith("company_tickers.json"):
            return Resp(js=SEC_TICKERS)
        if "CIK0000723125" in url:
            return Resp(js=MU_FACTS)
        if "CIK0001046179" in url:
            return Resp(js=TSM_FACTS)
        return Resp(js={"message": "not found"}, code=404)
    if "frankfurter" in url:
        CALLS.append((url, dict(params or {})))
        return fx_response(url, params or {})
    return _old_fake_get(url, params=params, timeout=timeout)


class FakeHttp:  # noqa: F811
    get = staticmethod(fake_get)
