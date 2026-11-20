"""DART 오픈API에서 사업보고서 재무제표를 가져와 비교 지표를 계산한다.

화면(app.py)과 분리해 두어서, 이 파일만으로도 테스트하고 다른 곳에 재사용할 수 있다.
데이터 출처: 금융감독원 전자공시시스템(DART) 오픈API (https://opendart.fss.or.kr)
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

import requests

API = "https://opendart.fss.or.kr/api/"
VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
TIMEOUT = 30

# 가져올 계정. DART 표준 계정 ID를 먼저 찾고, 없으면 계정 이름으로 찾는다.
METRICS = [
    {"key": "rev", "label": "매출액", "sj": ("IS", "CIS"), "ids": ("Revenue",),
     "names": (r"^매출액$", r"^수익\(매출액\)$", r"^매출액\(수익\)$", r"^영업수익$", r"^매출$", r"^수익$")},
    {"key": "op", "label": "영업이익", "sj": ("IS", "CIS"), "ids": ("OperatingIncomeLoss",),
     "names": (r"^영업이익(\(손실\))?$", r"^영업손익$")},
    {"key": "net", "label": "당기순이익", "sj": ("IS", "CIS"), "ids": ("ProfitLoss",),
     "names": (r"^당기순이익(\(손실\))?$", r"^당기순손익$", r"^연결당기순이익(\(손실\))?$")},
    {"key": "assets", "label": "자산총계", "sj": ("BS",), "ids": ("Assets",), "names": (r"^자산총계$",)},
    {"key": "liab", "label": "부채총계", "sj": ("BS",), "ids": ("Liabilities",), "names": (r"^부채총계$",)},
    {"key": "equity", "label": "자본총계", "sj": ("BS",), "ids": ("Equity",), "names": (r"^자본총계$",)},
    {"key": "ca", "label": "유동자산", "sj": ("BS",), "ids": ("CurrentAssets",), "names": (r"^유동자산$",)},
    {"key": "cl", "label": "유동부채", "sj": ("BS",), "ids": ("CurrentLiabilities",), "names": (r"^유동부채$",)},
]
METRIC_LABEL = {m["key"]: m["label"] for m in METRICS}

# 비교 지표. better: 높을수록 좋음(high) / 낮을수록 좋음(low) / 판단 안 함(None)
RATIOS = [
    {"key": "growth", "label": "매출 성장률", "better": "high", "unit": "%",
     "desc": "(올해 매출 − 작년 매출) ÷ 작년 매출. 회사가 얼마나 빨리 커지는지."},
    {"key": "op_margin", "label": "영업이익률", "better": "high", "unit": "%",
     "desc": "영업이익 ÷ 매출액. 본업으로 100원을 팔아 얼마를 남기는지."},
    {"key": "net_margin", "label": "순이익률", "better": "high", "unit": "%",
     "desc": "당기순이익 ÷ 매출액. 이자·세금까지 다 낸 뒤 최종적으로 남는 비율."},
    {"key": "debt", "label": "부채비율", "better": "low", "unit": "%",
     "desc": "부채총계 ÷ 자본총계. 낮을수록 빚 부담이 적고 재무가 안정적."},
    {"key": "current", "label": "유동비율", "better": "high", "unit": "%",
     "desc": "유동자산 ÷ 유동부채. 1년 안에 갚을 빚을 1년 안에 현금화할 자산으로 감당할 수 있는지."},
    {"key": "roe", "label": "ROE", "better": "high", "unit": "%",
     "desc": "당기순이익 ÷ 자본총계. 주주 돈으로 얼마나 벌었는지 (기말 자본으로 단순 계산)."},
    {"key": "roa", "label": "ROA", "better": "high", "unit": "%",
     "desc": "당기순이익 ÷ 자산총계. 가진 자산 전체로 얼마나 벌었는지 (기말 자산으로 단순 계산)."},
]
# ROE 분해(듀폰 분석): ROE = 순이익률 × 총자산회전율 × 재무레버리지
DUPONT = [
    {"key": "net_margin", "label": "순이익률", "unit": "%", "desc": "얼마나 남기며 파는가"},
    {"key": "turnover", "label": "총자산회전율", "unit": "회", "desc": "가진 자산으로 매출을 얼마나 일으키는가 (매출액 ÷ 자산총계)"},
    {"key": "leverage", "label": "재무레버리지", "unit": "배", "desc": "자기 돈 대비 자산을 얼마나 키웠는가, 즉 빚을 얼마나 썼는가 (자산총계 ÷ 자본총계)"},
]


class DartError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


# ───────────── 회사 목록 ─────────────

def fetch_corp_list(key: str, http=requests) -> list[dict]:
    """DART 전체 회사 목록(고유번호 파일)을 받아 [{code, name, eng, stock}] 로 돌려준다."""
    res = http.get(API + "corpCode.xml", params={"crtfc_key": key}, timeout=60)
    res.raise_for_status()
    data = res.content
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise DartError(*_error_from_text(data.decode("utf-8", "replace")))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next((n for n in zf.namelist() if n.lower().endswith("corpcode.xml")), zf.namelist()[0])
        xml = zf.read(name)
    return parse_corp_xml(xml)


def _error_from_text(text: str) -> tuple[str, str]:
    st = re.search(r"<status>([^<]*)</status>", text) or re.search(r'"status"\s*:\s*"([^"]*)"', text)
    msg = re.search(r"<message>([^<]*)</message>", text) or re.search(r'"message"\s*:\s*"([^"]*)"', text)
    return (st.group(1) if st else "?", msg.group(1) if msg else "인증키를 확인해 주세요.")


def parse_corp_xml(xml: bytes | str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for el in root.iter("list"):
        out.append({
            "code": (el.findtext("corp_code") or "").strip(),
            "name": (el.findtext("corp_name") or "").strip(),
            "eng": (el.findtext("corp_eng_name") or "").strip(),
            "stock": (el.findtext("stock_code") or "").strip(),
        })
    return out


def listed(corps: list[dict]) -> list[dict]:
    """상장사만 이름순으로."""
    return sorted((c for c in corps if c["stock"]), key=lambda c: c["name"])


# ───────────── 재무제표 ─────────────

def fetch_statements(key: str, corp_code: str, year: int, order: tuple[str, ...], http=requests):
    """사업보고서 전체 재무제표. order 순서대로(연결 CFS → 개별 OFS) 시도한다.
    돌려주는 값: (사용한 구분, 행 목록)"""
    last = ("013", "조회된 데이터가 없습니다.")
    for fs in order:
        res = http.get(API + "fnlttSinglAcntAll.json", params={
            "crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year),
            "reprt_code": "11011", "fs_div": fs}, timeout=TIMEOUT)
        try:
            j = res.json()
        except ValueError:
            last = (f"HTTP {res.status_code}", "응답을 읽지 못했어요.")
            continue
        if j.get("status") == "000" and j.get("list"):
            return fs, j["list"]
        last = (j.get("status", "?"), j.get("message", ""))
        if last[0] != "013":  # '데이터 없음'이 아닌 오류(키 오류 등)는 바로 멈춤
            break
    raise DartError(*last)


def parse_amount(s) -> float | None:
    if s is None:
        return None
    t = str(s).replace(",", "").strip()
    if t in ("", "-"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _norm_acct(s) -> str:
    t = re.sub(r"\s+", "", str(s or ""))
    return re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX0-9]+\.", "", t)


def _id_suffix(i) -> str:
    return re.sub(r"^(ifrs-full|ifrs_full|ifrs|dart)_", "", str(i or ""))


def extract_accounts(rows: list[dict]) -> dict:
    """행 목록에서 METRICS 계정을 찾아 {key: {cur, prev, prev2, id, nm}} (못 찾으면 None)."""
    out = {}
    for m in METRICS:
        cand = [r for r in rows if r.get("sj_div") in m["sj"]]
        hit = next((r for r in cand if _id_suffix(r.get("account_id")) in m["ids"]), None)
        if hit is None:
            for pat in m["names"]:
                hit = next((r for r in cand if re.match(pat, _norm_acct(r.get("account_nm")))), None)
                if hit:
                    break
        out[m["key"]] = None if hit is None else {
            "cur": parse_amount(hit.get("thstrm_amount")),
            "prev": parse_amount(hit.get("frmtrm_amount")),
            "prev2": parse_amount(hit.get("bfefrmtrm_amount")),
            "id": hit.get("account_id", ""), "nm": hit.get("account_nm", ""),
        }
    return out


# ───────────── 계산 ─────────────

def _div(x, y):
    return None if x is None or y is None or y == 0 else x / y


def ratios(v: dict, before: dict | None = None) -> dict:
    """한 해 금액 v(계정 key → 원)로 지표 계산. before = 전년도 금액(성장률용)."""
    rev, op, net = v.get("rev"), v.get("op"), v.get("net")
    assets, liab, eq = v.get("assets"), v.get("liab"), v.get("equity")
    pos_eq = eq is not None and eq > 0
    prev_rev = (before or {}).get("rev")
    return {
        "growth": None if rev is None or prev_rev in (None, 0) else (rev - prev_rev) / abs(prev_rev),
        "op_margin": _div(op, rev),
        "net_margin": _div(net, rev),
        "debt": _div(liab, eq) if pos_eq else None,
        "current": _div(v.get("ca"), v.get("cl")),
        "roe": _div(net, eq) if pos_eq else None,
        "roa": _div(net, assets),
        "turnover": _div(rev, assets),
        "leverage": _div(assets, eq) if pos_eq else None,
    }


def analyze_company(key: str, corp: dict, year: int, prefer: str = "CFS", http=requests) -> dict:
    """한 회사의 최근 5년 금액·지표를 만든다.
    사업보고서 하나에 당기·전기·전전기 3년치가 들어 있어서, year 와 year-2 보고서 두 개로 5년을 채운다.
    같은 해 숫자가 두 보고서에 다 있으면 더 최근 보고서(수정 반영된 숫자)를 쓴다."""
    order = ("CFS", "OFS") if prefer == "CFS" else ("OFS",)
    fs, rows = fetch_statements(key, corp["code"], year, order, http=http)
    acc = extract_accounts(rows)
    years: dict[int, dict] = {year - i: {} for i in range(5)}
    src: dict[int, str] = {}
    for k, x in acc.items():
        if x:
            for off, p in ((0, "cur"), (1, "prev"), (2, "prev2")):
                years[year - off][k] = x[p]
    rcept = rows[0].get("rcept_no", "")
    for y in (year, year - 1, year - 2):
        src[y] = rcept

    older_note = ""
    try:
        _, rows2 = fetch_statements(key, corp["code"], year - 2, (fs,), http=http)
        acc2 = extract_accounts(rows2)
        for k, x in acc2.items():
            if x:
                for off, p in ((3, "prev"), (4, "prev2")):
                    years[year - off][k] = x[p]
        r2 = rows2[0].get("rcept_no", "")
        src[year - 3] = src[year - 4] = r2
    except DartError as e:
        older_note = f"{year - 4}~{year - 3}년 수치 없음 (DART 응답: {e.message})"

    yr = {}
    for y in sorted(years):
        yr[y] = {"amount": years[y], "ratio": ratios(years[y], years.get(y - 1))}
    missing = [METRIC_LABEL[k] for k, x in acc.items() if x is None]
    return {
        "name": corp["name"], "code": corp["code"], "stock": corp.get("stock", ""),
        "fs": fs, "year": year, "years": yr, "src": src, "accounts": acc,
        "missing": missing, "older_note": older_note,
        "fell_back": prefer == "CFS" and fs == "OFS",
        "market": "KR", "currency": "KRW", "standard": "K-IFRS",
        # DART 사업보고서는 대부분 12월 결산이라 결산일을 12월 31일로 본다
        "period_end": {y: f"{y}-12-31" for y in yr if yr[y]["amount"]},
        "links": {y: VIEW + r for y, r in src.items() if r},
    }


def best_index(values: list, better: str) -> int:
    idx = -1
    for i, v in enumerate(values):
        if v is None:
            continue
        if idx < 0 or (v > values[idx] if better == "high" else v < values[idx]):
            idx = i
    return idx


def summary_lines(cos: list[dict]) -> list[str]:
    """지표별 1위·최하위를 숫자 그대로 문장으로. (해석은 넣지 않는다)"""
    lines = []
    for rt in RATIOS:
        vals = [c["years"][c["year"]]["ratio"][rt["key"]] for c in cos]
        b = best_index(vals, rt["better"])
        if b < 0:
            lines.append(f"**{rt['label']}** — 계산할 수 있는 회사가 없어요")
            continue
        w = best_index(vals, "low" if rt["better"] == "high" else "high")
        top = "가장 높음" if rt["better"] == "high" else "가장 낮음(안정적)"
        s = f"**{rt['label']}** — {top}: {cos[b]['name']} {vals[b] * 100:.1f}%"
        if sum(v is not None for v in vals) > 1 and w != b:
            bottom = "가장 낮음" if rt["better"] == "high" else "가장 높음"
            s += f" · {bottom}: {cos[w]['name']} {vals[w] * 100:.1f}%"
        lines.append(s)
    return lines


def ranking(cos: list[dict]) -> list[dict]:
    """지표별 우수·미흡 기업. best/worst = (회사명, 값) 또는 None."""
    out = []
    for rt in RATIOS:
        vals = [c["years"][c["year"]]["ratio"][rt["key"]] for c in cos]
        b = best_index(vals, rt["better"])
        w = best_index(vals, "low" if rt["better"] == "high" else "high")
        many = sum(v is not None for v in vals) > 1
        out.append({**rt,
                    "best": (cos[b]["name"], vals[b]) if b >= 0 else None,
                    "worst": (cos[w]["name"], vals[w]) if b >= 0 and many and w != b else None})
    return out
