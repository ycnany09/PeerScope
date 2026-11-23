"""분기 실적: 국내(DART 분기·반기 보고서)와 미국(SEC 10-Q) 수치를 분기 단위로 맞춘다.

- 분기 표기는 'YYYYQn' (예: 2026Q3).
- 4분기는 보고서가 따로 없어서 '연간 − 3분기 누적'으로 계산하고, derived 에 표시한다.
- 손익(매출·영업이익·순이익)은 3개월 금액, 재무상태(자산·부채·자본 등)는 분기말 잔액.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

import dart
import sec

PLAN_VERSION = 2  # 수집 계획이 바뀌면 올림 → 수집기가 분기 데이터를 다시 받음
FLOW = ("rev", "op", "net")
STOCK = ("assets", "liab", "equity", "ca", "cl")
QEND = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def label(y: int, q: int) -> str:
    return f"{y}Q{q}"


def parse(lb: str) -> tuple[int, int]:
    y, q = lb.split("Q")
    return int(y), int(q)


def shift(lb: str, n: int) -> str:
    """n 분기 앞(+)/뒤(−)."""
    y, q = parse(lb)
    i = y * 4 + (q - 1) + n
    return label(i // 4, i % 4 + 1)


def last_n(latest: str, n: int = 8) -> list[str]:
    return [shift(latest, -i) for i in range(n - 1, -1, -1)]


def latest_quarter(today: date | None = None) -> str:
    """오늘 기준 국내 보고서가 다 나왔을 가장 최근 분기.
    분기·반기 보고서는 분기 끝나고 45일, 사업보고서는 90일 안에 낸다 → 며칠 여유를 둔다."""
    t = today or date.today()
    md = (t.month, t.day)
    if md >= (11, 20):
        return label(t.year, 3)
    if md >= (8, 20):
        return label(t.year, 2)
    if md >= (5, 20):
        return label(t.year, 1)
    if md >= (4, 5):
        return label(t.year - 1, 4)
    return label(t.year - 1, 3)


def kr_quarter_end(lb: str) -> str:
    y, q = parse(lb)
    return f"{y}-{QEND[q]}"


# ───────────── 국내 ─────────────

def kr_plan(latest: str, have_fy: set[int]) -> list[tuple[int, int]]:
    """받아야 할 보고서 목록 [(연도, 분기)] (분기 4 = 사업보고서). 최신 보고서부터."""
    t, q = parse(latest)
    need = [(t, k) for k in range(min(q, 3), 0, -1)]
    if q < 3:  # 전년도 남은 분기(3개월 금액·누적)는 전년 보고서에서
        need += [(t - 1, k) for k in range(3, q, -1)]
    if q == 3:  # 전년 3분기 보고서 → 전전년 4분기 계산 → '직전 4개 분기 합계'(TTM 성장률)까지
        need.append((t - 1, 3))
    # 4분기 계산에 필요한 연간 실적: t-1년(항상), t년(최신이 4분기일 때)
    if q == 4 and t not in have_fy:
        need.insert(0, (t, 4))          # t년 사업보고서에 t-1년 연간도 같이 들어 있음
    elif (t - 1) not in have_fy:
        need.append((t - 1, 4))
    return need


def kr_quarters(key: str, corp: dict, latest: str, annual_years: dict | None = None,
                http=requests, prefer: str = "CFS") -> dict:
    """국내 한 회사의 최근 분기 실적. annual_years = 연간 수집 데이터 {연도: {계정: 금액}} (있으면 연간 보고서 재요청 생략)."""
    annual_years = {int(y): v for y, v in (annual_years or {}).items()}
    plan = kr_plan(latest, {y for y, v in annual_years.items() if all(v.get(k) is not None for k in FLOW)})
    order = ("CFS", "OFS") if prefer == "CFS" else ("OFS", "CFS")
    Q: dict[str, dict] = {}
    C: dict[tuple[int, int], dict] = {}
    FY: dict[int, dict] = {}
    src: dict[str, str] = {}
    fs = None
    for i, (y, k) in enumerate(plan):
        try:
            fs_used, rows = dart.fetch_statements(key, corp["code"], y, order if fs is None else (fs,), http=http,
                                                  reprt=dart.REPRT[k])
        except dart.DartError as e:
            if e.status == "013":
                if i == 0:  # 가장 최근 보고서가 없으면 이 회사는 분기 데이터 없음
                    raise
                continue
            raise
        if fs is None and fs_used != prefer:
            annual_years = {}  # 연간 수집 데이터와 연결/개별 구분이 다르면 섞지 않음
        fs = fs or fs_used
        hits = dart.find_rows(rows)
        rc = rows[0].get("rcept_no", "")
        amt = dart.parse_amount
        if k == 4:
            for key_ in FLOW:
                r = hits[key_]
                if r is not None:
                    FY.setdefault(y, {})[key_] = amt(r.get("thstrm_amount"))
                    FY.setdefault(y - 1, {}).setdefault(key_, amt(r.get("frmtrm_amount")))
            for key_ in STOCK:
                r = hits[key_]
                if r is not None:
                    Q.setdefault(label(y, 4), {}).setdefault(key_, amt(r.get("thstrm_amount")))
                    Q.setdefault(label(y - 1, 4), {}).setdefault(key_, amt(r.get("frmtrm_amount")))
            src.setdefault(label(y, 4), rc)
            continue
        for key_ in FLOW:
            r = hits[key_]
            if r is None:
                continue
            q3m = amt(r.get("thstrm_amount"))
            cum = amt(r.get("thstrm_add_amount"))
            pq = amt(r.get("frmtrm_q_amount"))
            pcum = amt(r.get("frmtrm_add_amount"))
            if k == 1:  # 1분기는 3개월 = 누적
                cum = q3m if cum is None else cum
                pq = pcum if pq is None else pq
                pcum = pq if pcum is None else pcum
            Q.setdefault(label(y, k), {}).setdefault(key_, q3m)
            Q.setdefault(label(y - 1, k), {}).setdefault(key_, pq)
            C.setdefault((y, k), {}).setdefault(key_, cum)
            C.setdefault((y - 1, k), {}).setdefault(key_, pcum)
        for key_ in STOCK:
            r = hits[key_]
            if r is None:
                continue
            Q.setdefault(label(y, k), {}).setdefault(key_, amt(r.get("thstrm_amount")))
            Q.setdefault(label(y - 1, 4), {}).setdefault(key_, amt(r.get("frmtrm_amount")))  # 전기말
        src.setdefault(label(y, k), rc)

    for y, v in annual_years.items():
        for key_ in FLOW:
            if v.get(key_) is not None:
                FY.setdefault(y, {}).setdefault(key_, v[key_])
        for key_ in STOCK:
            if v.get(key_) is not None:
                Q.setdefault(label(y, 4), {}).setdefault(key_, v[key_])

    derived = []
    for y, fy in FY.items():
        c9 = C.get((y, 3), {})
        got = False
        for key_ in FLOW:
            if fy.get(key_) is not None and c9.get(key_) is not None:
                Q.setdefault(label(y, 4), {})[key_] = fy[key_] - c9[key_]
                got = True
        if got:
            derived.append(label(y, 4))

    keep = set(last_n(latest, 8))
    q_out = {lb: {k_: v for k_, v in vals.items() if v is not None} for lb, vals in Q.items() if lb in keep}
    q_out = {lb: v for lb, v in q_out.items() if v}
    if not q_out.get(latest):
        raise dart.DartError("013", "조회된 데이터가 없습니다.")
    return {"status": "ok", "fs": fs, "latest": latest, "q": q_out,
            "derived": sorted(d for d in derived if d in q_out), "src": {k_: v for k_, v in src.items() if k_ in q_out}}


# ───────────── 미국 ─────────────

def _mid_label(start: date, end: date) -> str:
    mid = start + (end - start) / 2
    return label(mid.year, (mid.month - 1) // 3 + 1)


def us_quarters(facts_json: dict, n: int = 8) -> dict:
    """SEC companyfacts → 최근 분기 실적. 분기 표기는 기간 한가운데 날짜가 속한 달력 분기."""
    facts = facts_json.get("facts", {})
    cur = sec.detect_currency(facts)
    if not cur:
        raise dart.DartError("013", "SEC 데이터에서 재무 수치를 찾지 못했습니다.")
    forms = {"10-Q", "10-Q/A", "10-K", "10-K/A", "10-KT"}
    D = lambda s: date.fromisoformat(s)  # noqa: E731

    def vals(tax, name):
        c = facts.get(tax, {}).get(name)
        return [] if not c else [f for f in c.get("units", {}).get(cur, []) if f.get("form") in forms]

    def pick(cands):
        return max(cands, key=lambda f: (f.get("filed", ""), f.get("accn", ""))) if cands else None

    Q: dict[str, dict] = {}
    ends: dict[str, str] = {}
    derived: set[str] = set()
    for key_ in FLOW:
        # 연도별로 태그가 바뀌는 회사가 있어 기간마다 후보 태그를 순서대로 찾는다
        by_period: dict[tuple[str, str], dict] = {}
        for tax, name in sec.CONCEPTS[key_]:
            for f in vals(tax, name):
                if f.get("start"):
                    by_period.setdefault((f["start"], f["end"]), {}).setdefault(name, []).append(f)
        chosen: dict[tuple[str, str], float] = {}
        for per, by_name in by_period.items():
            for tax, name in sec.CONCEPTS[key_]:
                if name in by_name:
                    chosen[per] = float(pick(by_name[name])["val"])
                    break
        for (s, e), v in chosen.items():
            days = (D(e) - D(s)).days
            if 80 <= days <= 100:
                lb = _mid_label(D(s), D(e))
                Q.setdefault(lb, {})[key_] = v
                ends[lb] = e
        # 4분기 = 연간 − 같은 해 시작 9개월 누적
        for (s, e), fy in chosen.items():
            if not 340 <= (D(e) - D(s)).days <= 380:
                continue
            nine = [(e9, v) for (s9, e9), v in chosen.items() if s9 == s and 255 <= (D(e9) - D(s9)).days <= 290]
            if not nine:
                continue
            e9, v9 = max(nine)
            q4_start = D(e9) + timedelta(days=1)
            lb = _mid_label(q4_start, D(e))
            if key_ not in Q.get(lb, {}):
                Q.setdefault(lb, {})[key_] = fy - v9
                derived.add(lb)
            ends.setdefault(lb, e)
    end_to_lb = {e: lb for lb, e in ends.items()}
    for key_ in STOCK:
        best: dict[str, tuple] = {}
        for ci, (tax, name) in enumerate(sec.CONCEPTS[key_]):
            for f in vals(tax, name):
                if f.get("start") or f["end"] not in end_to_lb:
                    continue
                lb = end_to_lb[f["end"]]
                # 후보 순서가 앞선 태그 우선, 같은 태그면 최근 제출 우선
                rank = (-ci, f.get("filed", ""), f.get("accn", ""))
                if lb not in best or rank > best[lb][0]:
                    best[lb] = (rank, float(f["val"]))
        for lb, (_, v) in best.items():
            Q.setdefault(lb, {})[key_] = v
    for lb, v in Q.items():
        if "liab" not in v and "equity" in v and lb in ends:
            tot = pick([f for f in vals(*sec.TOTAL_LE) if not f.get("start") and f["end"] == ends[lb]])
            if tot is not None:
                v["liab"] = float(tot["val"]) - v["equity"]
    labels = sorted(lb for lb, v in Q.items() if any(k_ in v for k_ in FLOW))
    if not labels:
        raise dart.DartError("013", "SEC 데이터에 분기 실적이 없습니다.")
    latest = labels[-1]
    keep = set(last_n(latest, n))
    q_out = {lb: dict(Q[lb]) for lb in labels if lb in keep}
    return {"status": "ok", "currency": cur, "latest": latest, "q": q_out,
            "derived": sorted(d for d in derived if d in q_out), "period_end": {lb: ends[lb] for lb in q_out if lb in ends}}


# ───────────── 공통 계산 ─────────────

def ttm(entry: dict) -> dict | None:
    """최근 4개 분기 합계. 손익은 4개 분기가 다 있어야 계산, 재무상태는 최근 분기말."""
    latest = entry["latest"]
    four = last_n(latest, 4)
    q = entry["q"]
    out = {}
    for k_ in FLOW:
        vs = [q.get(lb, {}).get(k_) for lb in four]
        if all(v is not None for v in vs):
            out[k_] = sum(vs)
    for k_ in STOCK:
        v = q.get(latest, {}).get(k_)
        if v is not None:
            out[k_] = v
    if not any(k_ in out for k_ in FLOW):
        return None
    prev = {}
    for k_ in FLOW:
        vs = [q.get(lb, {}).get(k_) for lb in last_n(shift(latest, -4), 4)]
        if all(v is not None for v in vs):
            prev[k_] = sum(vs)
    return {"amount": out, "ratio": dart.ratios(out, prev or None), "period": f"{four[0]}~{four[-1]}"}


def yoy(entry: dict, lb: str, k_: str):
    a = entry["q"].get(lb, {}).get(k_)
    b = entry["q"].get(shift(lb, -4), {}).get(k_)
    return None if a is None or b in (None, 0) else (a - b) / abs(b)


def margin(entry: dict, lb: str, k_: str = "op"):
    v = entry["q"].get(lb, {})
    return None if v.get(k_) is None or not v.get("rev") or v["rev"] <= 0 else v[k_] / v["rev"]
