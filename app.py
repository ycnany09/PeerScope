"""피어스코프(PeerScope) — 경쟁사 재무 비교 Streamlit 웹앱

회사를 고르면 DART 사업보고서 숫자로 수익성·성장성·안정성을 비교하고,
5개년 추이와 ROE 분해(듀폰 분석)까지 보여 준다.
"""
from __future__ import annotations

import gzip
import html
import io
import json
import os
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dart
import fx
import sec

st.set_page_config(page_title="피어스코프 | 경쟁사 재무 비교", layout="wide")

# 회사 순서대로 고정 배정되는 색 (색은 순위가 아니라 회사를 따라간다). 색각 이상 검증 통과한 6색.
PALETTE = ["#1f5fbf", "#e07a2e", "#2a9d8f", "#8b5cc7", "#c9a227", "#b5508f"]
MAX_CO = 6
INK, SUB, RULE, BRAND = "#1a2433", "#5b6675", "#dde3ea", "#0b3b75"
FONT = "Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"

CSS = """<style>
:root{--ink:#1a2433;--sub:#5b6675;--rule:#dde3ea;--line:#edf0f4;--panel:#fff;--brand:#0b3b75;--tint:#e8f0fb;--up:#d1263b;--down:#1d5fd1}
header[data-testid="stHeader"]{display:none}
div[data-testid="stElementContainer"]:has(style){display:none}
.stMain{overflow-x:hidden}
.block-container{padding-top:0!important;padding-bottom:48px;max-width:1200px}
h1,h2,h3,p,li,td,th{word-break:keep-all}
.appbar{position:relative;left:50%;width:100vw;margin-left:-50vw;background:var(--brand);color:#fff;margin-bottom:20px}
.appbar .in{max-width:1200px;margin:0 auto;padding:14px 5rem;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}
.glyph{display:inline-flex;align-items:flex-end;gap:2px;height:16px}
.glyph i{display:block;width:4px;background:#fff;border-radius:1px}
.glyph i:nth-child(1){height:7px;opacity:.55}.glyph i:nth-child(2){height:11px;opacity:.8}.glyph i:nth-child(3){height:16px}
.brand b{font-size:16px;font-weight:700;letter-spacing:-.01em}
.brand .desc{font-size:13px;color:#c5d3e6;padding-left:12px;border-left:1px solid #3a6196}
.appbar .src{font-size:12px;color:#c5d3e6}
@media (max-width:640px){.appbar .in{padding:12px 1rem}.brand .desc{display:none}}
[data-testid="stForm"]{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:14px 18px 16px}
[data-testid="stWidgetLabel"] p{font-size:12px!important;font-weight:600;color:var(--sub)}
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--panel)}
.rhead{margin:22px 0 4px}
.rtitle{font-size:20px;font-weight:700;color:var(--ink);letter-spacing:-.015em}
.rsub{font-size:13px;color:var(--sub);margin-top:2px}
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:6px;margin:10px 0 6px}
.ptitle{font-size:14px;font-weight:700;color:var(--ink);padding:12px 14px 0}
.pnote{font-size:12px;color:var(--sub);padding:8px 14px 12px}
.scroll{overflow-x:auto}
table.grid{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;margin-top:8px}
table.grid th{font-weight:600;color:var(--sub);text-align:right;padding:8px 12px;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);background:#f8fafc;white-space:nowrap;vertical-align:bottom;line-height:1.35}
table.grid td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap;color:var(--ink)}
table.grid tr:last-child td{border-bottom:none}
table.grid .l{text-align:left}
table.grid td.wrap{white-space:normal;color:var(--sub);min-width:260px}
table.grid td.best{background:var(--tint);color:var(--brand);font-weight:700}
table.grid td.co{font-weight:600}
table.grid .unit{display:block;font-weight:400;font-size:11px;color:#8a94a3}
table.grid a{color:var(--brand);text-decoration:none;font-weight:600}
.up{color:var(--up)!important}.down{color:var(--down)!important}.flat{color:var(--sub)!important}
.mk{display:inline-block;font-size:10.5px;font-weight:600;color:#6b7686;border:1px solid var(--rule);border-radius:3px;padding:0 4px;margin-left:6px;vertical-align:1px}
.sw{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:8px;vertical-align:1px}
.notice{background:#fff8eb;border:1px solid #f1dcb3;border-radius:6px;padding:10px 14px;font-size:13px;color:#7a5410;margin:12px 0 0}
.notice div+div{margin-top:4px}
.info{background:var(--panel);border:1px dashed var(--rule);border-radius:6px;padding:28px 18px;text-align:center;color:var(--sub);font-size:14px;margin-top:14px}
.foot{font-size:12px;color:#8a94a3;margin-top:28px;border-top:1px solid var(--rule);padding-top:12px;line-height:1.7}
.stTabs [data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid var(--rule)}
.stTabs [data-baseweb="tab"]{padding:10px 14px;font-weight:600;font-size:14px}
.stTabs [data-baseweb="tab"][aria-selected="false"] p{color:var(--sub)}
</style>"""


def secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:  # secrets 파일 자체가 없을 때
        return ""


def get_key() -> str:
    return secret("DART_API_KEY")


def default_year() -> int:
    t = date.today()
    # 12월 결산 회사의 사업보고서는 보통 이듬해 3월 말까지 나온다 → 5월부터는 작년 실적 사용
    return t.year - 1 if t.month >= 5 else t.year - 2


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_corps(key: str) -> list[dict]:
    return dart.listed(dart.fetch_corp_list(key))


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_company(key: str, corp: dict, year: int, prefer: str) -> dict:
    return dart.analyze_company(key, corp, year, prefer)


KR_CACHE = os.environ.get("PEERSCOPE_KR_CACHE",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kr_financials.json.gz"))


@st.cache_data(show_spinner=False)
def load_kr_cache(path: str, mtime: float) -> dict:
    """collect_kr.py 로 한국 PC에서 미리 모은 국내 재무 데이터. (파일이 바뀌면 mtime 이 달라져 다시 읽음)"""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_us_list(ua: str) -> list[dict]:
    return sec.fetch_tickers(ua)


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_us(ua: str, comp: dict, year: int) -> dict:
    return sec.analyze_company(ua, comp, year)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fx_latest(base: str, quote: str):
    return fx.latest(base, quote)


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def fx_series(base: str, quote: str, start: str, end: str):
    return fx.series(base, quote, start, end)


# ───────────── 숫자·HTML 도우미 ─────────────

e = html.escape


def n_pct(v) -> str:
    return "–" if v is None else f"{v * 100:.1f}%"


def n_won(v) -> str:
    return "–" if v is None else f"{v:,.0f}"


def delta(v, unit: str) -> str:
    """한국 증권 화면 관례: 상승 빨강 ▲, 하락 파랑 ▼ (좋고 나쁨이 아니라 방향)."""
    if v is None:
        return '<span class="flat">–</span>'
    x = v * 100
    if abs(x) < 0.05:
        return f'<span class="flat">0.0{unit}</span>'
    cls, mark = ("up", "▲") if x > 0 else ("down", "▼")
    return f'<span class="{cls}">{mark} {abs(x):.1f}{unit}</span>'


def sw(color: str) -> str:
    return f'<span class="sw" style="background:{color}"></span>'


def th(label: str, unit: str = "", left: bool = False) -> str:
    u = f'<span class="unit">{e(unit)}</span>' if unit else ""
    return f'<th class="{"l" if left else ""}">{e(label)}{u}</th>'


def panel(title: str, table_html: str, note: str = "") -> str:
    t = f'<div class="ptitle">{e(title)}</div>' if title else ""
    n = f'<div class="pnote">{note}</div>' if note else ""
    return f'<div class="panel">{t}<div class="scroll">{table_html}</div>{n}</div>'


def show(html_text: str):
    st.markdown(html_text, unsafe_allow_html=True)


def style_fig(fig: go.Figure, y_fmt: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        template="simple_white", height=height, margin=dict(l=8, r=8, t=30, b=8),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family=FONT, size=12, color=SUB),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None, font=dict(color=INK)),
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, color=INK)),
    )
    fig.update_yaxes(tickformat=y_fmt, showgrid=True, gridcolor="#edf0f4", linecolor="#cfd6de",
                     zeroline=True, zerolinecolor="#b8c1cc", ticks="")
    fig.update_xaxes(type="category", showgrid=False, linecolor="#cfd6de", ticks="")
    return fig


# ───────────── 머리말 ─────────────

show(CSS)
show('<div class="appbar"><div class="in"><div class="brand"><span class="glyph"><i></i><i></i><i></i></span>'
     '<b>피어스코프</b><span class="desc">국내·미국 공시 기반 동종업계 재무지표 분석</span></div>'
     '<div class="src">출처: DART, SEC EDGAR</div></div></div>')

KEY = get_key()
CORPS, kr_msg, KR = [], "", None
if os.path.exists(KR_CACHE):
    try:
        KR = load_kr_cache(KR_CACHE, os.path.getmtime(KR_CACHE))
        CORPS = KR["corps"]
    except Exception:
        KR = None
        kr_msg = "국내 데이터 파일(data/kr_financials.json.gz)을 읽지 못했습니다. 수집기를 다시 실행해 올려 주세요."
elif not KEY:
    kr_msg = "국내 기업을 조회하려면 Secrets에 DART_API_KEY(DART 오픈API 인증키)를 추가하세요."
else:
    try:
        with st.spinner("DART 상장사 목록을 불러오는 중입니다."):
            CORPS = load_corps(KEY)
    except dart.DartError as ex:
        kr_msg = (ex.message if ex.status == "NET"
                  else f"DART 회사 목록을 받지 못했습니다. {ex.message} (코드 {ex.status})")
    except Exception as ex:  # 그 밖의 오류 (인증키가 보이지 않게 가림)
        kr_msg = f"DART 회사 목록을 처리하지 못했습니다. {dart.scrub(ex)}"

LABEL = {f"{c['name']} ({c['stock']})": c for c in CORPS}
UA = secret("SEC_USER_AGENT")
US_LABEL, us_msg = {}, ""
if not UA:
    us_msg = "미국 기업을 조회하려면 Secrets에 SEC_USER_AGENT(이름과 이메일)를 추가하세요."
else:
    try:
        US_LABEL = {f"{c['title']} ({c['ticker']})": c for c in load_us_list(UA)}
    except Exception as ex:
        us_msg = f"SEC 기업 목록을 받지 못했습니다. ({dart.scrub(ex)})"

this_year = date.today().year
YEARS = list(range(this_year - 1, 2018, -1))  # 5개년을 보려면 기준연도는 2019년부터

with st.form("pick"):
    m1, m2 = st.columns(2)
    picked = m1.multiselect("국내 기업 (DART)", list(LABEL), max_selections=MAX_CO,
                            placeholder="회사명 또는 종목코드 검색", disabled=not LABEL,
                            help=kr_msg or "DART에 사업보고서를 내는 국내 상장사")
    picked_us = m2.multiselect("미국 상장 기업 (SEC)", list(US_LABEL), max_selections=MAX_CO,
                               placeholder="영문 회사명 또는 티커 검색 (예: MU, AAPL)",
                               disabled=not US_LABEL, help=us_msg or "미국 SEC에 연간 보고서를 내는 기업")
    c1, c2, _, c3 = st.columns([2, 2.4, 4, 1.6], vertical_alignment="bottom")
    dy = default_year()
    year = c1.selectbox("기준 사업연도", YEARS, index=YEARS.index(dy) if dy in YEARS else 0,
                        help="사업보고서(연간) 기준. 기준연도를 포함해 5개년을 조회합니다. "
                             "미국 기업은 결산일이 속한 회계연도 기준입니다 (1~3월 결산은 직전 연도).")
    basis = c2.radio("재무제표 (국내)", ["연결 우선", "개별"], horizontal=True, disabled=KR is not None,
                     help=("수집 데이터는 연결재무제표 우선 기준입니다 (연결이 없으면 개별)." if KR is not None
                           else "연결: 종속회사 포함 / 개별: 해당 법인 단독"))
    go_btn = c3.form_submit_button("조회", type="primary", width="stretch")
    if KR is not None:
        st.caption(f"국내 데이터: {KR['collected_at'][:10]} 수집, {KR['base_year']}년 사업보고서까지 반영")
    for msg in (kr_msg, us_msg):
        if msg:
            st.caption(msg)

if go_btn:
    total = len(picked) + len(picked_us)
    if total == 0 or total > MAX_CO:
        show('<div class="notice"><div>' + ("비교할 회사를 1개 이상 선택하세요." if total == 0 else
             f"국내와 미국 기업을 합쳐 최대 {MAX_CO}개까지 비교할 수 있습니다. (현재 {total}개)") + "</div></div>")
        st.session_state.pop("result", None)
        st.stop()
    jobs = [("KR", LABEL[lb]) for lb in picked] + [("US", US_LABEL[lb]) for lb in picked_us]
    cos, errors = [], []
    bar = st.progress(0.0, text="재무제표 조회 중")
    for i, (mk, comp) in enumerate(jobs):
        nm = comp["name"] if mk == "KR" else comp["title"]
        bar.progress(i / len(jobs), text=f"{nm} 재무제표 조회 중")
        try:
            if mk == "KR" and KR is not None:
                entry = KR["companies"].get(comp["code"])
                if entry is None:
                    raise dart.DartError("CACHE", "수집 데이터에 없는 회사입니다. 수집기를 다시 실행하면 추가됩니다.")
                cos.append(dart.company_from_cache(entry, comp, int(year), int(KR["base_year"])))
            elif mk == "KR":
                cos.append(load_company(KEY, comp, int(year), "CFS" if basis == "연결 우선" else "OFS"))
            else:
                cos.append(load_us(UA, comp, int(year)))
        except dart.DartError as ex:
            if mk == "US" or ex.status in ("CACHE", "ERR"):
                why = ex.message
            elif ex.status == "013":
                why = f"{year}년 사업보고서 재무제표가 DART에 없습니다 (금융업·신규 상장사는 제공되지 않을 수 있음)"
            else:
                why = f"DART 오류 {ex.status}: {ex.message}"
            errors.append((nm, why))
        except Exception as ex:
            errors.append((nm, f"연결 오류: {dart.scrub(ex)}"))
    bar.empty()
    st.session_state["result"] = {"cos": cos, "errors": errors, "year": int(year), "basis": basis}

res = st.session_state.get("result")
if not res:
    show('<div class="info">비교할 회사를 선택하고 <b>조회</b>를 누르세요.<br>'
         '같은 업종의 경쟁사끼리 비교할 때 가장 의미 있는 결과가 나옵니다. 국내와 미국 기업을 함께 고를 수 있습니다.</div>')
    st.stop()

cos: list[dict] = res["cos"]
year: int = res["year"]

# 조회 실패·참고 사항
msgs = [f"<b>{e(n)}</b> 조회 제외: {e(w)}" for n, w in res["errors"]]
for c in cos:
    n = []
    if c["fell_back"]:
        n.append("연결재무제표가 없어 개별 기준 적용")
    if c["missing"]:
        n.append("미확인 계정: " + ", ".join(c["missing"]))
    if c["older_note"]:
        n.append(c["older_note"])
    pe = c["period_end"].get(year, "")
    if c["market"] == "US" and pe and not pe.endswith("-12-31"):
        n.append(f"결산일 {pe}")
    if n:
        msgs.append(f"<b>{e(c['name'])}</b> " + " / ".join(e(x) for x in n))
if {c["market"] for c in cos} == {"KR", "US"}:
    msgs.append("국내(K-IFRS)와 미국(US GAAP) 기업은 회계 기준이 달라 영업이익 등 일부 항목의 정의가 다를 수 있습니다.")
if msgs:
    show('<div class="notice">' + "".join(f"<div>{m}</div>" for m in msgs) + "</div>")
if not cos:
    st.stop()

COLOR = {c["name"]: PALETTE[i % len(PALETTE)] for i, c in enumerate(cos)}
names = [c["name"] for c in cos]
YRS = sorted(cos[0]["years"])
AMT_KEYS = ("rev", "op", "net", "assets", "liab", "equity")


def cur(c, part, k, y=None):
    return c["years"][y or year][part][k]


def basis_of(c) -> str:
    return c["standard"] if c["market"] == "US" else ("연결" if c["fs"] == "CFS" else "개별")


def co_cell(c) -> str:
    return (f'<td class="l co">{sw(COLOR[c["name"]])}{e(c["name"])}'
            f'<span class="mk">{"미국" if c["market"] == "US" else "국내"}</span></td>')


# ───────────── 보고서 머리 + 통화 전환 ─────────────

basis_txt = ("국내는 연결재무제표 우선" if KR is not None or res.get("basis", "연결 우선") == "연결 우선"
             else "국내는 개별재무제표")
show(f'<div class="rhead"><div class="rtitle">{year} 회계연도 재무 비교</div>'
     f'<div class="rsub">{e(", ".join(names))} / {len(cos)}개사 / {basis_txt}</div></div>')

cc1, cc2, _, cdl = st.columns([2.2, 2.8, 3, 1.4], vertical_alignment="bottom")
show_cur = cc1.radio("금액 표시", ["원화로 표기", "달러로 표기"], horizontal=True, key="show_cur")
rate_mode = cc2.radio("적용 환율", ["현재 환율", "연도별 환율"], horizontal=True, key="rate_mode",
                      help="현재 환율: 모든 연도에 가장 최근 기준환율을 적용합니다.\n\n"
                           "연도별 환율: 매출·이익은 해당 회계연도 1년 평균, 자산·부채·자본은 결산일 환율을 적용합니다.")
TARGET = "KRW" if show_cur == "원화로 표기" else "USD"
UNIT = "억원" if TARGET == "KRW" else "백만 달러"
DIV = 1e8 if TARGET == "KRW" else 1e6
fx_used: dict = {}
fx_fail: set = set()


def factor(c, y, k):
    """회사 c 의 y년 계정 k 금액에 곱할 환율. 못 구하면 None."""
    src = c["currency"]
    if src == TARGET:
        return 1.0
    try:
        if rate_mode == "현재 환율":
            r, d = fx_latest(src, TARGET)
            fx_used[(src, TARGET)] = (r, d)
            return r
        pe = c["period_end"].get(y)
        ends = sorted(c["period_end"].values())
        if not pe:
            return None
        start = (date.fromisoformat(ends[0]) - timedelta(days=370)).isoformat()
        ser = fx_series(src, TARGET, start, ends[-1])
        r = fx.period_average(ser, pe) if k in sec.FLOW else fx.on_date(ser, pe)
        if r is not None:
            fx_used[(src, TARGET)] = None
        return r
    except Exception:
        fx_fail.add(f"{src}→{TARGET}")
        return None


def conv(c, k, y=None):
    """표시 통화로 바꾼 금액. 원본이 없거나 환율을 못 구하면 None."""
    y = y or year
    v = c["years"][y]["amount"].get(k)
    if v is None:
        return None
    f = factor(c, y, k)
    return None if f is None else v * f


def n_amt(v) -> str:
    return "–" if v is None else f"{v / DIV:,.0f}"


# ───────────── 내려받기용 표 ─────────────

table = pd.DataFrame([{
    "회사": c["name"], "시장": "미국" if c["market"] == "US" else "국내", "기준": basis_of(c),
    **{f"{dart.METRIC_LABEL[k]}({UNIT})": None if conv(c, k) is None else conv(c, k) / DIV for k in AMT_KEYS},
    **{r["label"]: cur(c, "ratio", r["key"]) for r in dart.RATIOS},
} for c in cos])
trend = pd.DataFrame([{
    "회사": c["name"], "연도": y,
    **{f"{dart.METRIC_LABEL[k]}({UNIT})": None if conv(c, k, y) is None else conv(c, k, y) / DIV for k in ("rev", "op", "net")},
    **{x["label"]: c["years"][y]["ratio"][x["key"]] for x in dart.RATIOS},
} for c in cos for y in YRS])
raw = pd.DataFrame([{
    "회사": c["name"], "통화": c["currency"], "항목": m["label"],
    "계정 ID": (c["accounts"][m["key"]] or {}).get("id", ""),
    "계정명": (c["accounts"][m["key"]] or {}).get("nm", "(미확인)"),
    **{str(y): c["years"][y]["amount"].get(m["key"]) for y in reversed(YRS)},
    "공시 원문": c["links"].get(year, ""),
} for c in cos for m in dart.METRICS])


def excel_bytes() -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        table.to_excel(w, sheet_name="비교표", index=False)
        trend.to_excel(w, sheet_name="5개년 추이", index=False)
        raw.to_excel(w, sheet_name="원본 데이터(보고 통화)", index=False)
    return buf.getvalue()


with cdl:
    st.download_button("엑셀 내려받기", excel_bytes(), file_name=f"피어스코프_재무비교_{year}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")


def fx_note() -> str:
    parts = []
    if rate_mode == "현재 환율":
        for (a, b), (r, d) in fx_used.items():
            # 1보다 작은 환율(원→달러)은 거꾸로 읽는 게 쉬워서 1 달러 = ○원 꼴로 보여 준다
            parts.append(f"1 {b} = {1 / r:,.2f} {a}" if r < 1 else f"1 {a} = {r:,.2f} {b}")
        if parts:
            d = next(iter(fx_used.values()))[1]
            txt = "적용 환율 " + ", ".join(parts) + f" ({d} 유럽중앙은행 기준환율)."
        else:
            txt = ""
    else:
        txt = ("연도별 환율 적용: 매출·이익은 회계연도 1년 평균, 자산·부채·자본은 결산일 기준환율(유럽중앙은행)."
               if fx_used else "")
    if fx_fail:
        txt += f" 환율을 받지 못해 {', '.join(sorted(fx_fail))} 금액은 표시하지 않았습니다."
    return txt.strip()


# ───────────── 주요 지표 ─────────────

rows = []
for c in cos:
    now, prev = c["years"][year]["ratio"], c["years"][year - 1]["ratio"]

    def dd(k):
        return None if now[k] is None or prev[k] is None else now[k] - prev[k]

    rows.append(
        f'<tr>{co_cell(c)}<td>{e(basis_of(c))}</td>'
        f'<td>{n_amt(conv(c, "rev"))}</td><td>{delta(now["growth"], "%")}</td>'
        f'<td>{n_amt(conv(c, "op"))}</td>'
        f'<td>{n_pct(now["op_margin"])}</td><td>{delta(dd("op_margin"), "%p")}</td>'
        f'<td>{n_pct(now["debt"])}</td><td>{delta(dd("debt"), "%p")}</td>'
        f'<td>{n_pct(now["roe"])}</td></tr>')
kpi = ('<table class="grid"><thead><tr>' + th("회사", left=True) + th("기준") + th("매출액", UNIT) + th("전년비")
       + th("영업이익", UNIT) + th("영업이익률") + th("전년비") + th("부채비율") + th("전년비") + th("ROE")
       + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
note = "▲ 상승 ▼ 하락 (전년 대비). 비율 증감은 %p 단위이며, 성장률과 비율은 각 회사의 보고 통화 기준입니다."
fxn = fx_note()
show(panel("주요 지표", kpi, note + (f"<br>{e(fxn)}" if fxn else "")))

# ───────────── 탭 ─────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs(["지표 순위", "상세 비교표", "5개년 추이", "ROE 분해", "원본 데이터"])

with tab1:
    def cell(x):
        if not x:
            return '<td class="l flat">–</td>'
        return f'<td class="l">{sw(COLOR[x[0]])}{e(x[0])} <b>{n_pct(x[1])}</b></td>'

    rk = []
    for r in dart.ranking(cos):
        if r["best"]:
            rk.append(f'<tr><td class="l co">{e(r["label"])}</td>{cell(r["best"])}{cell(r["worst"])}'
                      f'<td class="l wrap">{e(r["desc"])}</td></tr>')
        else:
            rk.append(f'<tr><td class="l co">{e(r["label"])}</td><td class="l flat" colspan="2">계산 가능한 회사 없음</td>'
                      f'<td class="l wrap">{e(r["desc"])}</td></tr>')
    rank_tbl = ('<table class="grid"><thead><tr>' + th("지표", left=True) + th("우수", left=True)
                + th("미흡", left=True) + th("계산식과 의미", left=True) + "</tr></thead><tbody>" + "".join(rk) + "</tbody></table>")
    show(panel("", rank_tbl, "부채비율은 낮을수록 우수로 봅니다. 수치의 원인은 사업보고서와 산업 동향으로 별도 확인이 필요합니다."))

with tab2:
    head = (th("회사", left=True) + th("기준") + "".join(th(dart.METRIC_LABEL[k], UNIT) for k in AMT_KEYS)
            + "".join(th(r["label"]) for r in dart.RATIOS))
    best = {r["key"]: dart.best_index([cur(c, "ratio", r["key"]) for c in cos], r["better"]) for r in dart.RATIOS}
    body = []
    for i, c in enumerate(cos):
        tds = "".join(f"<td>{n_amt(conv(c, k))}</td>" for k in AMT_KEYS)
        tds += "".join(
            f'<td class="{"best" if best[r["key"]] == i and len(cos) > 1 else ""}">{n_pct(cur(c, "ratio", r["key"]))}</td>'
            for r in dart.RATIOS)
        body.append(f'<tr>{co_cell(c)}<td>{e(basis_of(c))}</td>{tds}</tr>')
    show(panel("", f'<table class="grid"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>',
               "강조 표시는 지표별 우수 기업입니다 (부채비율은 낮을수록 우수)." + (f"<br>{e(fxn)}" if fxn else "")))

with tab3:
    options = {"매출액": ("amount", "rev"), "영업이익": ("amount", "op"), "당기순이익": ("amount", "net"),
               "영업이익률": ("ratio", "op_margin"), "매출 성장률": ("ratio", "growth"),
               "부채비율": ("ratio", "debt"), "ROE": ("ratio", "roe")}
    pick = st.radio("지표 선택", list(options), horizontal=True, label_visibility="collapsed")
    part, k = options[pick]
    is_amt = part == "amount"
    unit = UNIT if is_amt else "%"

    def val(c, y):
        if is_amt:
            v = conv(c, k, y)
            return None if v is None else v / DIV
        return c["years"][y]["ratio"].get(k)

    with st.container(border=True):
        show(f'<div class="ptitle" style="padding:2px 0 0">{e(pick)} 추이 <span style="font-weight:400;color:{SUB};font-size:12px">'
             f'({e(unit)})</span></div>')
        fig = go.Figure()
        for c in cos:
            fig.add_trace(go.Scatter(
                x=[str(y) for y in YRS], y=[val(c, y) for y in YRS], name=c["name"], mode="lines+markers",
                line=dict(width=2, color=COLOR[c["name"]]), marker=dict(size=7, color=COLOR[c["name"]]),
                hovertemplate=("%{y:,.0f} " + UNIT if is_amt else "%{y:.1%}") + "<extra>" + c["name"] + "</extra>"))
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(style_fig(fig, ",.0f" if is_amt else ".0%"), width="stretch", config={"displayModeBar": False})
        fmt = (lambda v: "–" if v is None else f"{v:,.0f}") if is_amt else n_pct
        tr = "".join(f"<tr>{co_cell(c)}" + "".join(f"<td>{fmt(val(c, y))}</td>" for y in YRS) + "</tr>" for c in cos)
        show(f'<div class="scroll"><table class="grid"><thead><tr>{th("회사", left=True)}'
             + "".join(th(str(y)) for y in YRS) + f"</tr></thead><tbody>{tr}</tbody></table></div>")
    st.caption("국내 기업은 기준연도와 2년 전 사업보고서, 미국 기업은 연간 보고서(10-K 등)의 수치로 구성했습니다. "
               "같은 연도가 여러 보고서에 있으면 가장 최근에 제출된 수치를 사용합니다.")

with tab4:
    with st.container(border=True):
        show('<div class="ptitle" style="padding:2px 0 0">ROE = 순이익률 × 총자산회전율 × 재무레버리지</div>'
             f'<div style="font-size:13px;color:{SUB};margin:4px 0 6px">같은 ROE라도 수익성, 자산 효율, 부채 활용 중 무엇에서 나오는지에 따라 의미가 다릅니다.</div>')
        dcols = st.columns(3)
        for dc, comp in zip(dcols, dart.DUPONT):
            vals = [cur(c, "ratio", comp["key"]) for c in cos]
            pct = comp["unit"] == "%"
            f = go.Figure(go.Bar(
                x=names, y=vals, marker=dict(color=[COLOR[n] for n in names], cornerradius=2),
                hovertemplate="%{x}: " + ("%{y:.1%}" if pct else "%{y:.2f}" + comp["unit"]) + "<extra></extra>",
                text=["–" if v is None else (f"{v * 100:.1f}%" if pct else f"{v:.2f}{comp['unit']}") for v in vals],
                textposition="outside", cliponaxis=False, textfont=dict(color=INK, size=12)))
            f.update_layout(title=dict(text=comp["label"], font=dict(size=13, color=INK), x=0, xanchor="left"),
                            showlegend=False, bargap=0.5)
            style_fig(f, ".0%" if pct else ".1f", height=280)
            f.update_yaxes(showticklabels=False, showgrid=False, linecolor="white")
            with dc:
                st.plotly_chart(f, width="stretch", config={"displayModeBar": False})
                st.caption(comp["desc"])

        def times(v, u):
            return "–" if v is None else f"{v:.2f}{u}"

        tr = "".join(
            f'<tr>{co_cell(c)}'
            f'<td><b>{n_pct(cur(c, "ratio", "roe"))}</b></td><td>{n_pct(cur(c, "ratio", "net_margin"))}</td>'
            f'<td>{times(cur(c, "ratio", "turnover"), "회")}</td><td>{times(cur(c, "ratio", "leverage"), "배")}</td></tr>'
            for c in cos)
        show(f'<div class="scroll"><table class="grid"><thead><tr>{th("회사", left=True)}{th("ROE")}{th("순이익률")}'
             f'{th("총자산회전율")}{th("재무레버리지")}</tr></thead><tbody>{tr}</tbody></table></div>')

with tab5:
    head = (th("회사", left=True) + th("통화") + th("항목", left=True) + th("계정 ID", left=True) + th("계정명", left=True)
            + "".join(th(str(y)) for y in reversed(YRS)) + th("공시 원문"))
    body = []
    for c in cos:
        url = c["links"].get(year)
        link = f'<a href="{e(url)}" target="_blank" rel="noopener">보기</a>' if url else "–"
        for m in dart.METRICS:
            acc = c["accounts"][m["key"]]
            body.append(
                f'<tr>{co_cell(c)}<td>{e(c["currency"])}</td><td class="l">{e(m["label"])}</td>'
                f'<td class="l flat">{e(acc["id"]) if acc else ""}</td><td class="l">{e(acc["nm"]) if acc else "(미확인)"}</td>'
                + "".join(f"<td>{n_won(c['years'][y]['amount'].get(m['key']))}</td>" for y in reversed(YRS))
                + f"<td>{link}</td></tr>")
    show(panel("", f'<table class="grid"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>',
               "공시 수치를 환율 변환 없이 각 회사의 보고 통화 그대로 표시합니다. 공시 원문 링크는 기준연도 보고서입니다."))

show('<div class="foot">데이터 출처: 금융감독원 전자공시시스템(DART) 오픈API, 미국 증권거래위원회(SEC) EDGAR, '
     '환율은 유럽중앙은행 기준환율(Frankfurter API).<br>'
     '업종과 회계 기준이 달라 수치만으로 기업의 우열을 단정할 수 없습니다. ROE와 ROA는 기말 잔액으로 단순 계산했습니다.</div>')
