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
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dart
import fx
import prices
import quarter
import sec
import us_names
from plotly.subplots import make_subplots

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
.pxlink{color:var(--brand);font-weight:600;text-decoration:none;border-bottom:1px solid var(--tint)}
.pxlink:hover{border-bottom-color:var(--brand)}
.pxlink:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:2px}
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
    facts = sec.fetch_facts(ua, comp["cik"])
    res = sec.analyze_company(ua, comp, year, facts_json=facts)
    try:
        res["quarters"] = quarter.us_quarters(facts)
    except dart.DartError:
        res["quarters"] = None
    return res


KR_QCACHE = os.path.join(os.path.dirname(KR_CACHE), "kr_quarterly.json.gz")


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_kr_quarters_live(key: str, corp: dict, latest: str):
    try:
        return quarter.kr_quarters(key, corp, latest)
    except dart.DartError:
        return None


@st.cache_data(ttl=60 * 60 * 3, show_spinner=False)
def load_prices(market: str, code: str, start: str, end: str, kr_key: str, us_key: str):
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if market == "KR":
        return prices.kr_prices(kr_key, code, s, e)
    return prices.us_prices(us_key, code, s, e)


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
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None, font=dict(color=INK),
                    itemclick=False, itemdoubleclick=False),  # 범례를 잘못 눌러 회사가 사라지지 않게
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, color=INK)),
        dragmode=False,  # 휴대폰에서 스크롤하다 끌면 확대되던 문제 방지 (눌러서 값 보기는 그대로)
    )
    fig.update_yaxes(tickformat=y_fmt, showgrid=True, gridcolor="#edf0f4", linecolor="#cfd6de",
                     zeroline=True, zerolinecolor="#b8c1cc", ticks="")
    fig.update_xaxes(type="category", showgrid=False, linecolor="#cfd6de", ticks="")
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


PCFG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False}  # 확대·축소 없이 보기 전용


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

KRQ = None
if KR is not None and os.path.exists(KR_QCACHE):
    try:
        KRQ = load_kr_cache(KR_QCACHE, os.path.getmtime(KR_QCACHE))
    except Exception:
        KRQ = None

LABEL = {f"{c['name']} ({c['stock']})": c for c in CORPS}
UA = secret("SEC_USER_AGENT")
US_LABEL, us_msg = {}, ""
if not UA:
    us_msg = "미국 기업을 조회하려면 Secrets에 SEC_USER_AGENT(이름과 이메일)를 추가하세요."
else:
    try:
        US_LABEL = {us_names.label(c["title"], c["ticker"]): c for c in load_us_list(UA)}
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
                               placeholder="한글·영문 회사명 또는 티커 (예: 엔비디아, 코카콜라, AAPL)",
                               disabled=not US_LABEL, help=us_msg or "미국 SEC에 연간 보고서를 내는 기업")
    c2, _, c3 = st.columns([2.4, 6, 1.6], vertical_alignment="bottom")
    basis = c2.radio("재무제표 (국내)", ["연결 우선", "개별"], horizontal=True, disabled=KR is not None,
                     help=("수집 데이터는 연결재무제표 우선 기준입니다 (연결이 없으면 개별)." if KR is not None
                           else "연결: 종속회사 포함 / 개별: 해당 법인 단독"))
    go_btn = c3.form_submit_button("조회", type="primary", width="stretch")
    if KR is not None:
        qtxt = f", 분기는 {quarter.parse(KRQ['latest'])[0]}년 {quarter.parse(KRQ['latest'])[1]}분기까지" if KRQ else ""
        st.caption(f"국내 데이터: {KR['collected_at'][:10]} 수집, {KR['base_year']}년 사업보고서까지 반영{qtxt}")
    for msg in (kr_msg, us_msg):
        if msg:
            st.caption(msg)

if go_btn:
    total = len(picked) + len(picked_us)
    if total == 0 or total > MAX_CO:
        show('<div class="notice"><div>' + ("비교할 회사를 1개 이상 선택하세요." if total == 0 else
             f"국내와 미국 기업을 합쳐 최대 {MAX_CO}개까지 비교할 수 있습니다. (현재 {total}개)") + "</div></div>")
        st.session_state.pop("query", None)
        st.stop()
    jobs = [("KR", LABEL[lb]) for lb in picked] + [("US", US_LABEL[lb]) for lb in picked_us]
    st.session_state["query"] = {"jobs": jobs, "basis": basis}

query = st.session_state.get("query")
if not query:
    show('<div class="info">비교할 회사를 선택하고 <b>조회</b>를 누르세요.<br>'
         '같은 업종의 경쟁사끼리 비교할 때 가장 의미 있는 결과가 나옵니다. 국내와 미국 기업을 함께 고를 수 있습니다.</div>')
    st.stop()


def qname_(lb: str) -> str:
    y_, q_ = quarter.parse(lb)
    return f"{y_} {q_}Q"


def load_all(jobs, year: int, basis: str, with_bar: bool):
    """고른 회사들의 연간 데이터(year 기준 5개년)와 분기 데이터를 불러온다."""
    cos, errors = [], []
    bar = st.progress(0.0, text="재무제표 조회 중") if with_bar else None
    for i, (mk, comp) in enumerate(jobs):
        nm = comp["name"] if mk == "KR" else comp["title"]
        if bar:
            bar.progress(i / len(jobs), text=f"{nm} 재무제표 조회 중")
        try:
            if mk == "KR" and KR is not None:
                entry = KR["companies"].get(comp["code"])
                if entry is None:
                    raise dart.DartError("CACHE", "수집 데이터에 없는 회사입니다. 수집기를 다시 실행하면 추가됩니다.")
                c_ = dart.company_from_cache(entry, comp, int(year), int(KR["base_year"]))
                qe = (KRQ or {}).get("companies", {}).get(comp["code"])
                c_["quarters"] = qe if qe and qe.get("status") == "ok" else None
                cos.append(c_)
            elif mk == "KR":
                c_ = dict(load_company(KEY, comp, int(year), "CFS" if basis == "연결 우선" else "OFS"))
                c_["quarters"] = load_kr_quarters_live(KEY, comp, quarter.latest_quarter())
                cos.append(c_)
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
    if bar:
        bar.empty()
    return cos, errors


# ───────────── 기준 기간 ─────────────

PMODES = {"최근 4개 분기": "TTM", "한 분기": "ONE", "분기 범위": "RANGE", "분기 직접 선택": "PICK", "사업연도": "annual"}
pb1, pb2 = st.columns([5, 4], vertical_alignment="bottom")
pmode = pb1.radio(
    "기준 기간", list(PMODES), horizontal=True, key="pmode",
    help="최근 4개 분기: 회사마다 가장 최근 분기까지 1년 합계(TTM).\n\n"
         "한 분기: 고른 분기 3개월 실적.\n\n"
         "분기 범위: 시작~끝 분기를 이어서 합계.\n\n"
         "분기 직접 선택: 체크한 분기들의 합계.\n\n"
         "사업연도: 1년 실적 보고서 기준.\n\n"
         "분기 보기의 증감은 1년 전 같은 분기(들)와 비교합니다. 미국 기업은 회계분기의 가운데 달이 속한 "
         "달력 분기로 맞춥니다 (예: 5~7월 분기 → 2분기).")
MODE = PMODES[pmode]
dy = default_year()
if MODE == "annual":
    if st.session_state.get("p_year") not in YEARS:
        st.session_state["p_year"] = dy if dy in YEARS else YEARS[0]
    load_year = pb2.selectbox("사업연도", YEARS, key="p_year", format_func=lambda v: f"{v} 사업연도",
                              help="그해를 포함해 5개년 추이를 보여 줍니다. 미국 기업은 결산일이 속한 회계연도 기준입니다 "
                                   "(1~3월 결산은 직전 연도).")
else:
    load_year = dy  # 분기 보기에서도 5개년 추이·원본 데이터는 가장 최근 사업연도 기준

cos_annual, load_errors = load_all(query["jobs"], int(load_year), query["basis"], with_bar=bool(go_btn))
res = {"errors": load_errors, "basis": query["basis"]}
year_annual: int = int(load_year)

QOPTS = sorted({lb for c in cos_annual for lb in ((c.get("quarters") or {}).get("q") or {})},
               key=quarter.parse, reverse=True)
sel_labels = None  # None = 회사별 최근 4개 분기 (TTM)
if MODE in ("ONE", "RANGE", "PICK"):
    if not QOPTS:
        show('<div class="notice"><div>고른 회사 중 분기 데이터가 있는 회사가 없습니다. '
             '<b>사업연도</b> 보기를 이용하세요.</div></div>')
        st.stop()
    # 모든 회사에 있는 가장 최근 분기를 기본값으로
    common = [lb for lb in QOPTS if all(lb in ((c.get("quarters") or {}).get("q") or {})
                                        for c in cos_annual if c.get("quarters"))]
    base = common[0] if common else QOPTS[0]

    def _ensure(key, default, ok):
        if not ok(st.session_state.get(key)):
            st.session_state[key] = default

    if MODE == "ONE":
        _ensure("p_q", base, lambda v: v in QOPTS)
        sel_labels = [pb2.selectbox("분기", QOPTS, key="p_q", format_func=qname_)]
    elif MODE == "RANGE":
        start_default = quarter.shift(base, -3) if quarter.shift(base, -3) in QOPTS else QOPTS[-1]
        _ensure("p_from", start_default, lambda v: v in QOPTS)
        _ensure("p_to", base, lambda v: v in QOPTS)
        r1, r2 = pb2.columns(2)
        a_ = r1.selectbox("시작 분기", QOPTS, key="p_from", format_func=qname_)
        b_ = r2.selectbox("끝 분기", QOPTS, key="p_to", format_func=qname_)
        lo, hi = sorted([a_, b_], key=quarter.parse)
        sel_labels = []
        lb = lo
        while quarter.parse(lb) <= quarter.parse(hi):
            sel_labels.append(lb)
            lb = quarter.shift(lb, 1)
    else:
        _ensure("p_pick", [base], lambda v: isinstance(v, list) and all(x in QOPTS for x in v))
        picked_q = pb2.multiselect("분기 (여러 개 선택 가능)", QOPTS, key="p_pick", format_func=qname_,
                                   placeholder="합계로 볼 분기를 고르세요")
        if not picked_q:
            show('<div class="info">합계로 볼 분기를 하나 이상 고르세요.</div>')
            st.stop()
        sel_labels = quarter.sort_labels(picked_q)


def _qend(c, lb):
    q = c.get("quarters") or {}
    return (q.get("period_end") or {}).get(lb) or (quarter.kr_quarter_end(lb) if c["market"] == "KR" else None)


def ptext(labels: list[str]) -> str:
    if len(labels) == 1:
        return qname_(labels[0])
    if quarter.contiguous(labels):
        return f"{qname_(labels[0])}~{qname_(labels[-1])}"
    return ", ".join(qname_(x) for x in labels)


def q_view(c, key: int, labels: list[str] | None):
    """회사 c 를 '고른 분기 합계' 기준으로 바꾼 사본. labels=None 이면 그 회사의 최근 4개 분기.
    연간 화면 코드를 그대로 쓰도록 같은 모양(years[key], years[key-1])으로 만든다. 못 만들면 (None, 이유)."""
    qd = c.get("quarters")
    if not qd:
        return None, "분기 데이터가 없어"
    if labels is None:
        labels = quarter.last_n(qd["latest"], 4)
    lacking = [lb for lb in labels if lb not in qd["q"]]
    if lacking:
        return None, ", ".join(qname_(x) for x in lacking) + " 데이터가 없어"
    t = quarter.combine(qd, labels)
    if not t:
        return None, "고른 분기의 손익 데이터가 없어"
    pe = _qend(c, t["labels"][-1])
    pe_prev = _qend(c, t["prev_labels"][-1]) or (pe and str(int(pe[:4]) - 1) + pe[4:])
    v = dict(c)
    v["years"] = {key: {"amount": t["amount"], "ratio": t["ratio"]},
                  key - 1: {"amount": t["prev_amount"], "ratio": t["prev_ratio"]}}
    v["period_end"] = {y_: d for y_, d in ((key, pe), (key - 1, pe_prev)) if d}
    v["year"] = key
    v["q_sel"] = {key: t["labels"], key - 1: t["prev_labels"]}
    v["q_labels"] = t["labels"]
    return v, None


if MODE == "annual":
    cos, year, excluded = cos_annual, year_annual, []
else:
    year = date.today().year
    cos, excluded = [], []
    for c in cos_annual:
        tv, why = q_view(c, year, sel_labels)
        if tv:
            cos.append(tv)
        else:
            excluded.append((c["name"], why))
N_Q = len(sel_labels) if sel_labels else 4


# 조회 실패·참고 사항
msgs = [f"<b>{e(n)}</b> 조회 제외: {e(w)}" for n, w in res["errors"]]
msgs += [f"<b>{e(n)}</b> {e(w)} 이 보기에서 제외 (사업연도 보기에서는 표시)" for n, w in excluded]
for c in cos:
    n = []
    if c["fell_back"]:
        n.append("연결재무제표가 없어 개별 기준 적용")
    if c["missing"]:
        n.append("미확인 계정: " + ", ".join(c["missing"]))
    if c["older_note"]:
        n.append(c["older_note"])
    pe = c["period_end"].get(year, "")
    if MODE == "TTM":
        n.append("기간 " + ptext(c["q_labels"]))
    if MODE != "annual" and c["market"] == "US" and pe and pe[5:] not in quarter.QEND.values():
        n.append(f"실제 분기말 {pe}")
    elif MODE == "annual" and c["market"] == "US" and pe and not pe.endswith("-12-31"):
        n.append(f"결산일 {pe}")
    if n:
        msgs.append(f"<b>{e(c['name'])}</b> " + " / ".join(e(x) for x in n))
if {c["market"] for c in cos} == {"KR", "US"}:
    msgs.append("국내(K-IFRS)와 미국(US GAAP) 기업은 회계 기준이 달라 영업이익 등 일부 항목의 정의가 다를 수 있습니다.")
if msgs:
    show('<div class="notice">' + "".join(f"<div>{m}</div>" for m in msgs) + "</div>")
if not cos:
    st.stop()

COLOR = {c["name"]: PALETTE[i % len(PALETTE)] for i, c in enumerate(cos_annual)}
names = [c["name"] for c in cos]
YRS = sorted(cos_annual[0]["years"])
AMT_KEYS = ("rev", "op", "net", "assets", "liab", "equity")


def cur(c, part, k, y=None):
    return c["years"][y or year][part].get(k)


def basis_of(c) -> str:
    return c["standard"] if c["market"] == "US" else ("연결" if c["fs"] == "CFS" else "개별")


def co_cell(c) -> str:
    return (f'<td class="l co">{sw(COLOR[c["name"]])}{e(c["name"])}'
            f'<span class="mk">{"미국" if c["market"] == "US" else "국내"}</span></td>')


# ───────────── 보고서 머리 + 통화 전환 ─────────────

basis_txt = ("국내는 연결재무제표 우선" if KR is not None or res.get("basis", "연결 우선") == "연결 우선"
             else "국내는 개별재무제표")
if MODE == "TTM":
    _ps = {tuple(c["q_labels"]) for c in cos}
    title = "최근 4개 분기 재무 비교 (" + (ptext(list(next(iter(_ps)))) if len(_ps) == 1 else "회사별 가장 최근 4개 분기") + ")"
elif MODE == "annual":
    title = f"{year} 회계연도 재무 비교"
elif N_Q == 1:
    title = f"{ptext(sel_labels)} 재무 비교 (분기 실적)"
elif quarter.contiguous(sel_labels):
    title = f"{ptext(sel_labels)} 재무 비교 ({N_Q}개 분기 합계)"
else:
    title = f"선택 분기 재무 비교 ({ptext(sel_labels)} 합계)"
show(f'<div class="rhead"><div class="rtitle">{e(title)}</div>'
     f'<div class="rsub">{e(", ".join(names))} / {len(cos)}개사 / {basis_txt}</div></div>')

cc1, cc2, _, cdl = st.columns([2.2, 2.8, 3, 1.4], vertical_alignment="bottom")
show_cur = cc1.radio("금액 표시", ["원화로 표기", "달러로 표기"], horizontal=True, key="show_cur")
rate_mode = cc2.radio("적용 환율", ["현재 환율", "기간별 환율"], horizontal=True, key="rate_mode",
                      help="현재 환율: 모든 기간에 가장 최근 기준환율을 적용합니다.\n\n"
                           "기간별 환율: 매출·이익은 그 기간 평균 환율(분기 보기는 분기마다 따로 환산해 합산), "
                           "자산·부채·자본은 기간 말일 환율을 적용합니다.")
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
        sel = (c.get("q_sel") or {}).get(y)
        if sel:  # 분기 보기: 분기마다 그 분기 환율로 바꿔 더한 값과 같아지도록
            if k not in sec.FLOW:
                return qfactor(c, sel[-1], k)
            raw = [((c.get("quarters") or {}).get("q", {}).get(lb) or {}).get(k) for lb in sel]
            fs = [qfactor(c, lb, k) for lb in sel]
            if any(v is None for v in raw) or any(f is None for f in fs):
                return None
            den = sum(raw)
            return sum(v * f for v, f in zip(raw, fs)) / den if den else sum(fs) / len(fs)
        pe = c["period_end"].get(y)
        if not pe:
            return None
        ends = all_ends(c)
        start = (date.fromisoformat(ends[0]) - timedelta(days=370)).isoformat()
        ser = fx_series(src, TARGET, start, ends[-1])
        r = fx.period_average(ser, pe) if k in sec.FLOW else fx.on_date(ser, pe)
        if r is not None:
            fx_used[(src, TARGET)] = None
        return r
    except Exception:
        fx_fail.add(f"{src}→{TARGET}")
        return None


def q_end(c, lb):
    q = c.get("quarters") or {}
    return (q.get("period_end") or {}).get(lb) or (quarter.kr_quarter_end(lb) if c["market"] == "KR" else None)


def all_ends(c) -> list[str]:
    ends = list(c["period_end"].values())
    q = c.get("quarters") or {}
    ends += [e_ for e_ in (q_end(c, lb) for lb in q.get("q", {})) if e_]
    return sorted(ends)


def qfactor(c, lb, k):
    src = c["currency"]
    if src == TARGET:
        return 1.0
    if rate_mode == "현재 환율":
        return factor(c, year, k)
    pe = q_end(c, lb)
    if not pe:
        return None
    try:
        ends = all_ends(c)
        start = (date.fromisoformat(ends[0]) - timedelta(days=370)).isoformat()
        ser = fx_series(src, TARGET, start, ends[-1])
        r = fx.period_average(ser, pe, days=91) if k in sec.FLOW else fx.on_date(ser, pe)
        if r is not None:
            fx_used[(src, TARGET)] = None
        return r
    except Exception:
        fx_fail.add(f"{src}→{TARGET}")
        return None


def qconv(c, lb, k):
    v = ((c.get("quarters") or {}).get("q", {}).get(lb) or {}).get(k)
    if v is None:
        return None
    f = qfactor(c, lb, k)
    return None if f is None else v * f


def qname(lb: str) -> str:
    y, q = quarter.parse(lb)
    return f"{y} {q}Q"


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
} for c in cos_annual for y in YRS])
raw = pd.DataFrame([{
    "회사": c["name"], "통화": c["currency"], "항목": m["label"],
    "계정 ID": (c["accounts"][m["key"]] or {}).get("id", ""),
    "계정명": (c["accounts"][m["key"]] or {}).get("nm", "(미확인)"),
    **{str(y): c["years"][y]["amount"].get(m["key"]) for y in reversed(YRS)},
    "공시 원문": c["links"].get(year_annual, ""),
} for c in cos_annual for m in dart.METRICS])


def excel_bytes() -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        table.to_excel(w, sheet_name="비교표", index=False)
        trend.to_excel(w, sheet_name="5개년 추이", index=False)
        raw.to_excel(w, sheet_name="원본 데이터(보고 통화)", index=False)
        qrows = [{"회사": c["name"], "분기": lb, **{f"{dart.METRIC_LABEL[k]}({UNIT})": (None if qconv(c, lb, k) is None
                                                                                   else qconv(c, lb, k) / DIV)
                                                 for k in quarter.FLOW},
                  "계산값(4분기)": "예" if lb in c["quarters"]["derived"] else ""}
                 for c in cos if c.get("quarters") for lb in sorted(c["quarters"]["q"])]
        if qrows:
            pd.DataFrame(qrows).to_excel(w, sheet_name="분기 실적", index=False)
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
        txt = (("기간별 환율 적용: 매출·이익은 회계연도 1년 평균, 자산·부채·자본은 결산일 기준환율(유럽중앙은행)."
                if MODE == "annual" else
                "기간별 환율 적용: 매출·이익은 분기마다 그 분기 평균 환율로 바꿔 합산, 자산·부채·자본은 마지막 분기말 기준환율(유럽중앙은행).")
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
_vs = {"TTM": "직전 4개 분기 대비", "annual": "전년비"}.get(MODE, "전년 동기 대비")
kpi = ('<table class="grid"><thead><tr>' + th("회사", left=True) + th("기준") + th("매출액", UNIT) + th(_vs)
       + th("영업이익", UNIT) + th("영업이익률") + th(_vs) + th("부채비율") + th(_vs) + th("ROE")
       + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
_cmp = {"TTM": "직전 4개 분기 합계 대비", "annual": "전년 대비"}.get(
    MODE, "1년 전 같은 분기 대비" if N_Q == 1 else "1년 전 같은 분기들의 합계 대비")
note = ("▲ 상승 ▼ 하락 (" + _cmp + "). "
        "비율 증감은 %p 단위이며, 성장률과 비율은 각 회사의 보고 통화 기준입니다."
        + (" 부채비율·ROE는 마지막 분기말 잔액 기준입니다." if MODE != "annual" else "")
        + (f" ROE·ROA·총자산회전율은 {N_Q}개 분기 실적을 1년 기준으로 환산했습니다 (×4/{N_Q})."
           if MODE != "annual" and N_Q != 4 else "")
        + (" 1년 전 데이터가 없는 분기는 증감이 '–'로 표시됩니다." if MODE in ("ONE", "RANGE", "PICK") else ""))
fxn = fx_note()
show(panel("주요 지표", kpi, note + (f"<br>{e(fxn)}" if fxn else "")))

# ───────────── 탭 ─────────────

(tab1, tab2, tab3, tab_q, tab_pos, tab4, tab_px, tab5) = st.tabs(
    ["지표 순위", "상세 비교표", "5개년 추이", "분기 실적", "포지셔닝·구조", "ROE 분해", "주가", "원본 데이터"])

with tab1:
    def cell(x):
        if not x:
            return '<td class="l flat">–</td>'
        return f'<td class="l">{sw(COLOR[x[0]])}{e(x[0])} <b>{n_pct(x[1])}</b></td>'

    rk = []
    for r in dart.ranking(cos):
        if r["key"] == "growth" and MODE != "annual":
            r = {**r, "desc": "(이번 기간 매출 − 비교 기간 매출) ÷ 비교 기간 매출. 비교 기간은 "
                 + ("직전 4개 분기." if MODE == "TTM" else "1년 전 같은 분기(들).")}
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
        for c in cos_annual:
            fig.add_trace(go.Scatter(
                x=[str(y) for y in YRS], y=[val(c, y) for y in YRS], name=c["name"], mode="lines+markers",
                line=dict(width=2, color=COLOR[c["name"]]), marker=dict(size=7, color=COLOR[c["name"]]),
                hovertemplate=("%{y:,.0f} " + UNIT if is_amt else "%{y:.1%}") + "<extra>" + c["name"] + "</extra>"))
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(style_fig(fig, ",.0f" if is_amt else ".0%"), width="stretch", config=PCFG)
        fmt = (lambda v: "–" if v is None else f"{v:,.0f}") if is_amt else n_pct
        tr = "".join(f"<tr>{co_cell(c)}" + "".join(f"<td>{fmt(val(c, y))}</td>" for y in YRS) + "</tr>" for c in cos_annual)
        show(f'<div class="scroll"><table class="grid"><thead><tr>{th("회사", left=True)}'
             + "".join(th(str(y)) for y in YRS) + f"</tr></thead><tbody>{tr}</tbody></table></div>")
    if MODE != "annual":
        seg_note = f"연간 실적(사업보고서) 기준 {YRS[0]}~{YRS[-1]}년 추이입니다. "
    else:
        seg_note = ""
    st.caption(seg_note + "국내 기업은 기준연도와 2년 전 사업보고서, 미국 기업은 연간 보고서(10-K 등)의 수치로 구성했습니다. "
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
                st.plotly_chart(f, width="stretch", config=PCFG)
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

# ───────────── 분기 실적 ─────────────

with tab_q:
    qcos = [c for c in cos_annual if c.get("quarters")]
    if not qcos:
        show('<div class="info">분기 데이터가 있는 회사가 없습니다.<br>국내 기업은 수집기를 다시 실행해 분기 데이터(kr_quarterly.json.gz)를 올리면 표시됩니다.</div>')
    else:
        missing_q = [c["name"] for c in cos_annual if not c.get("quarters")]
        # 최근 분기 표
        rows_q = []
        for c in qcos:
            qd = c["quarters"]
            lb = qd["latest"]
            now_m, prev_m = quarter.margin(qd, lb), quarter.margin(qd, quarter.shift(lb, -4))
            dm = None if now_m is None or prev_m is None else now_m - prev_m
            rows_q.append(
                f'<tr>{co_cell(c)}<td>{qname(lb)}{" *" if lb in qd["derived"] else ""}</td>'
                f'<td>{n_amt(qconv(c, lb, "rev"))}</td><td>{delta(quarter.yoy(qd, lb, "rev"), "%")}</td>'
                f'<td>{n_amt(qconv(c, lb, "op"))}</td><td>{n_pct(now_m)}</td><td>{delta(dm, "%p")}</td>'
                f'<td>{n_amt(qconv(c, lb, "net"))}</td></tr>')
        show(panel("최근 분기 실적", '<table class="grid"><thead><tr>' + th("회사", left=True) + th("분기") + th("매출액", UNIT)
                   + th("전년 동기비") + th("영업이익", UNIT) + th("영업이익률") + th("전년 동기비") + th("순이익", UNIT)
                   + "</tr></thead><tbody>" + "".join(rows_q) + "</tbody></table>",
                   "전년 동기비는 1년 전 같은 분기와 비교한 값입니다. * 표시는 연간 실적에서 3분기 누적을 빼서 계산한 4분기입니다."))
        # TTM 표
        rows_t = []
        for c in qcos:
            qd = c["quarters"]
            t = quarter.ttm(qd)
            if not t:
                rows_t.append(f'<tr>{co_cell(c)}<td class="l flat" colspan="8">최근 4개 분기가 모두 있지 않아 계산할 수 없습니다.</td></tr>')
                continue
            four = quarter.last_n(qd["latest"], 4)
            tconv = {}
            for k_ in quarter.FLOW:
                vs = [qconv(c, lb, k_) for lb in four]
                tconv[k_] = None if any(v is None for v in vs) or k_ not in t["amount"] else sum(vs)
            r = t["ratio"]
            rows_t.append(
                f'<tr>{co_cell(c)}<td>{qname(four[0])}~{qname(four[-1])}</td>'
                f'<td>{n_amt(tconv["rev"])}</td><td>{delta(r["growth"], "%")}</td><td>{n_amt(tconv["op"])}</td>'
                f'<td>{n_pct(r["op_margin"])}</td><td>{n_pct(r["net_margin"])}</td><td>{n_pct(r["roe"])}</td>'
                f'<td>{n_pct(r["debt"])}</td></tr>')
        show(panel("최근 4개 분기 합계 (TTM)", '<table class="grid"><thead><tr>' + th("회사", left=True) + th("기간")
                   + th("매출액", UNIT) + th("직전 4개 분기 대비") + th("영업이익", UNIT) + th("영업이익률") + th("순이익률")
                   + th("ROE") + th("부채비율") + "</tr></thead><tbody>" + "".join(rows_t) + "</tbody></table>",
                   "아직 연간 보고서가 나오지 않은 최근 1년 실적을 비교할 때 씁니다. ROE·부채비율은 최근 분기말 자본·부채 기준입니다."))
        # 분기 차트
        qopts = {"매출액": ("amt", "rev"), "영업이익": ("amt", "op"), "순이익": ("amt", "net"),
                 "영업이익률": ("margin", "op"), "순이익률": ("margin", "net"), "매출 전년 동기비": ("yoy", "rev")}
        qpick = st.radio("분기 지표", list(qopts), horizontal=True, label_visibility="collapsed", key="qpick")
        kind, k_ = qopts[qpick]
        labels = sorted({lb for c in qcos for lb in c["quarters"]["q"]})[-8:]

        def qval(c, lb):
            qd = c["quarters"]
            if kind == "amt":
                v = qconv(c, lb, k_)
                return None if v is None else v / DIV
            if kind == "margin":
                return quarter.margin(qd, lb, k_)
            return quarter.yoy(qd, lb, k_)

        with st.container(border=True):
            unit_txt = UNIT if kind == "amt" else "%"
            show(f'<div class="ptitle" style="padding:2px 0 0">분기별 {e(qpick)} <span style="font-weight:400;color:{SUB};font-size:12px">'
                 f'({e(unit_txt)})</span></div>')
            fig = go.Figure()
            xs = [qname(lb) for lb in labels]
            for c in qcos:
                ys = [qval(c, lb) for lb in labels]
                hov = ("%{y:,.0f} " + UNIT if kind == "amt" else "%{y:.1%}") + "<extra>" + c["name"] + "</extra>"
                if kind == "amt":
                    fig.add_trace(go.Bar(x=xs, y=ys, name=c["name"], marker=dict(color=COLOR[c["name"]], cornerradius=2),
                                         hovertemplate=hov))
                else:
                    fig.add_trace(go.Scatter(x=xs, y=ys, name=c["name"], mode="lines+markers", connectgaps=False,
                                             line=dict(width=2, color=COLOR[c["name"]]),
                                             marker=dict(size=7, color=COLOR[c["name"]]), hovertemplate=hov))
            fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08, hovermode="x unified")
            st.plotly_chart(style_fig(fig, ",.0f" if kind == "amt" else ".0%"), width="stretch",
                            config=PCFG)
            tr = "".join(f"<tr>{co_cell(c)}" + "".join(
                f"<td>{('–' if qval(c, lb) is None else (f'{qval(c, lb):,.0f}' if kind == 'amt' else n_pct(qval(c, lb))))}</td>"
                for lb in labels) + "</tr>" for c in qcos)
            show(f'<div class="scroll"><table class="grid"><thead><tr>{th("회사", left=True)}'
                 + "".join(th(qname(lb)) for lb in labels) + f"</tr></thead><tbody>{tr}</tbody></table></div>")
        notes_q = ["국내 기업은 분기·반기 보고서의 3개월 실적, 미국 기업은 10-Q 보고서 수치입니다.",
                   "미국 기업의 회계 분기는 기간 한가운데 날짜가 속한 달력 분기로 맞췄습니다 (예: 8~10월 분기 → 3분기)."]
        der = sorted({qname(d) for c in qcos for d in c["quarters"]["derived"]})
        if der:
            notes_q.append("4분기(" + ", ".join(der) + ")는 연간 실적에서 3분기 누적을 빼서 계산했습니다.")
        if missing_q:
            notes_q.append("분기 데이터 없음: " + ", ".join(missing_q))
        st.caption(" ".join(notes_q))

# ───────────── 포지셔닝·구조 ─────────────

with tab_pos:
    def median(vals):
        v = sorted(x for x in vals if x is not None)
        if not v:
            return None
        m = len(v) // 2
        return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2

    def pos_map(title, xk, yk, xlabel, ylabel, desc):
        pts = [(c, cur(c, "ratio", xk), cur(c, "ratio", yk)) for c in cos]
        pts = [p for p in pts if p[1] is not None and p[2] is not None]
        with st.container(border=True):
            show(f'<div class="ptitle" style="padding:2px 0 0">{e(title)}</div>'
                 f'<div style="font-size:13px;color:{SUB};margin:4px 0 6px">{e(desc)}</div>')
            if len(pts) < 2:
                st.caption("두 회사 이상 값이 있어야 비교할 수 있습니다.")
                return
            revs = [conv(c, "rev") or 0 for c, _, _ in pts]
            mx = max(revs) or 1
            fig = go.Figure()
            for (c, x, y), rv in zip(pts, revs):
                fig.add_trace(go.Scatter(
                    x=[x], y=[y], mode="markers+text", name=c["name"], cliponaxis=False,
                    text=[c["name"] if len(c["name"]) <= 14 else c["name"][:13] + "…"], textposition="top center",
                    textfont=dict(color=INK, size=12),
                    marker=dict(size=14 + 36 * (rv / mx) ** 0.5, color=COLOR[c["name"]], opacity=0.85,
                                line=dict(color="white", width=2)),
                    hovertemplate=f"{c['name']}<br>{xlabel}: %{{x:.1%}}<br>{ylabel}: %{{y:.1%}}<extra></extra>"))
            mxv, myv = median([p[1] for p in pts]), median([p[2] for p in pts])
            fig.add_vline(x=mxv, line=dict(color="#b8c1cc", dash="dot", width=1))
            fig.add_hline(y=myv, line=dict(color="#b8c1cc", dash="dot", width=1))
            fig.update_layout(showlegend=False)
            style_fig(fig, ".0%", height=380)
            fig.update_layout(margin=dict(l=8, r=40, t=30, b=8))
            xs_, ys_ = [p[1] for p in pts], [p[2] for p in pts]
            padx = (max(xs_) - min(xs_)) * 0.22 or 0.05
            pady = (max(ys_) - min(ys_)) * 0.22 or 0.05
            fig.update_xaxes(type="linear", tickformat=".0%", title=dict(text=xlabel, font=dict(size=12)),
                             showgrid=True, gridcolor="#edf0f4", range=[min(xs_) - padx, max(xs_) + padx])
            fig.update_yaxes(range=[min(ys_) - pady, max(ys_) + pady * 1.4])
            fig.update_yaxes(title=dict(text=ylabel, font=dict(size=12)))
            st.plotly_chart(fig, width="stretch", config=PCFG)
            st.caption("점선은 비교 회사들의 중앙값, 원 크기는 매출액입니다.")

    pc1, pc2 = st.columns(2)
    with pc1:
        pos_map("성장성 × 수익성", "growth", "op_margin", "매출 성장률", "영업이익률",
                "오른쪽 위일수록 빠르게 크면서 많이 남기는 회사입니다.")
    with pc2:
        pos_map("재무 레버리지 × ROE", "debt", "roe", "부채비율", "ROE",
                "같은 ROE라도 오른쪽(부채비율 높음)이면 빚을 활용해 만든 수익일 가능성이 큽니다.")

    with st.container(border=True):
        show('<div class="ptitle" style="padding:2px 0 0">재무 구조</div>'
             f'<div style="font-size:13px;color:{SUB};margin:4px 0 6px">자산총계를 100으로 놓고 무엇으로 조달했고(부채·자본) 어떤 자산을 가졌는지(유동·비유동) 비교합니다.</div>')
        sc1, sc2 = st.columns(2)

        def stack(col, title, parts):
            rows_ = []
            for c in cos:
                a = cur(c, "amount", "assets")
                vals = [cur(c, "amount", k1) if k1 != "nca" else (None if a is None or cur(c, "amount", "ca") is None
                                                                  else a - cur(c, "amount", "ca")) for k1, _, _ in parts]
                if a and all(v is not None for v in vals):
                    rows_.append((c["name"], [v / a for v in vals]))
            with col:
                if not rows_:
                    st.caption(f"{title}: 계산할 수 있는 회사가 없습니다.")
                    return
                # 제목은 차트 밖(HTML)에 둔다: 차트 안 제목은 범례와 같은 자리에 겹쳐 그려짐
                show(f'<div style="font-size:13px;font-weight:700;color:{INK};margin:6px 0 0">{e(title)}</div>')
                f = go.Figure()
                for i, (_, lab, colr) in enumerate(parts):
                    f.add_trace(go.Bar(
                        y=[r[0] for r in rows_], x=[r[1][i] for r in rows_], name=lab, orientation="h",
                        marker=dict(color=colr, line=dict(color="white", width=2)),
                        text=[f"{r[1][i] * 100:.0f}%" for r in rows_], textposition="inside", insidetextanchor="middle",
                        textfont=dict(color="white" if i == 0 else INK, size=12),
                        hovertemplate="%{y} " + lab + ": %{x:.1%}<extra></extra>"))
                f.update_layout(barmode="stack", bargap=0.35)
                f.update_layout(legend=dict(traceorder="normal"))
                style_fig(f, ".0%", height=110 + 46 * len(rows_))
                f.update_xaxes(type="linear", range=[0, 1], showgrid=False, showticklabels=False)
                f.update_yaxes(type="category", autorange="reversed", showgrid=False)
                st.plotly_chart(f, width="stretch", config=PCFG)

        stack(sc1, "자금 조달: 부채 vs 자본", [("liab", "부채", "#0b3b75"), ("equity", "자본", "#c7d3e3")])
        stack(sc2, "자산 구성: 유동 vs 비유동", [("ca", "유동자산", "#0b3b75"), ("nca", "비유동자산", "#c7d3e3")])

# ───────────── 주가 ─────────────

with tab_px:
    KR_PX_KEY, US_PX_KEY = secret("DATA_GO_KR_KEY"), secret("TWELVE_DATA_KEY")
    # 외부 시세 사이트 바로가기: 링크만 걸어서 데이터 재배포 없이 누구나 볼 수 있음
    def px_links(c) -> str:
        code = str(c.get("stock") or "").strip()
        if not code:
            return '<span class="flat">–</span>'
        if c["market"] == "KR":
            # 네이버 증권 종목 주소는 휴대폰에서 증권 첫 화면으로 넘어가 버려서, PC·모바일 모두 되는 네이버 검색(주가 카드)으로 연결
            url, site = f"https://search.naver.com/search.naver?query={quote(c['name'] + ' 주가')}", "네이버"
        else:
            url, site = f"https://finance.yahoo.com/quote/{quote(code)}", "Yahoo Finance"
        return f'<a class="pxlink" href="{e(url)}" target="_blank" rel="noopener">{site}에서 주가 보기</a>'

    link_rows = "".join(f'<tr>{co_cell(c)}<td>{e(str(c.get("stock") or "–"))}</td>'
                        f'<td class="l">{px_links(c)}</td></tr>' for c in cos_annual)
    link_tbl = ('<table class="grid"><thead><tr>' + th("회사", left=True) + th("종목코드·티커")
                + th("시세 사이트", left=True) + "</tr></thead><tbody>" + link_rows + "</tbody></table>")
    if not KR_PX_KEY and not US_PX_KEY:
        show(panel("주가 바로가기", link_tbl,
                   "주가 차트는 데이터 제공처(한국거래소·Twelve Data)의 이용 조건상 공개 웹사이트에 직접 표시할 수 없어, "
                   "외부 시세 사이트로 연결합니다. 링크는 새 창에서 열립니다. "
                   "개인 PC에서 run_app.bat으로 실행하면 이 탭에 회사별 주가 수익률 비교 차트가 함께 나옵니다."))
    span = (st.radio("기간", ["3개월", "6개월", "1년", "3년"], index=2, horizontal=True, key="px_span",
                     label_visibility="collapsed") if (KR_PX_KEY or US_PX_KEY) else "1년")
    days = {"3개월": 92, "6개월": 183, "1년": 366, "3년": 1096}[span]
    end_d = date.today()
    start_d = end_d - timedelta(days=days)
    series, px_err = {}, []
    for c in cos:
        mkey = KR_PX_KEY if c["market"] == "KR" else US_PX_KEY
        if not mkey:
            if KR_PX_KEY or US_PX_KEY:
                px_err.append(f"<b>{e(c['name'])}</b> " + ("공공데이터포털 인증키(DATA_GO_KR_KEY)를 설정하면 표시됩니다."
                                                       if c["market"] == "KR" else
                                                       "Twelve Data 키(TWELVE_DATA_KEY)를 설정하면 표시됩니다."))
            continue
        try:
            series[c["name"]] = load_prices(c["market"], c["stock"], start_d.isoformat(), end_d.isoformat(),
                                            KR_PX_KEY, US_PX_KEY)
        except prices.PriceError as ex:
            px_err.append(f"<b>{e(c['name'])}</b> {e(str(ex))}")
        except Exception as ex:
            px_err.append(f"<b>{e(c['name'])}</b> 시세를 불러오지 못했습니다. {e(dart.scrub(ex))}")
    if px_err:
        show('<div class="notice">' + "".join(f"<div>{m}</div>" for m in px_err) + "</div>")
    if series:
        with st.container(border=True):
            show('<div class="ptitle" style="padding:2px 0 0">주가 수익률 비교 <span style="font-weight:400;color:'
                 f'{SUB};font-size:12px">(기간 첫날 = 0%)</span></div>')
            fig = go.Figure()
            for c in cos:
                rows_ = series.get(c["name"])
                if not rows_:
                    continue
                base = next((r["close"] for r in rows_ if r["close"]), None)
                fig.add_trace(go.Scatter(
                    x=[r["date"] for r in rows_], y=[(r["close"] / base - 1) if base and r["close"] else None for r in rows_],
                    name=c["name"], mode="lines", line=dict(width=2, color=COLOR[c["name"]]),
                    hovertemplate="%{y:+.1%}<extra>" + c["name"] + "</extra>"))
            fig.update_layout(hovermode="x unified")
            style_fig(fig, "+.0%")
            fig.update_xaxes(type="date")
            st.plotly_chart(fig, width="stretch", config=PCFG)
            tr = []
            for c in cos:
                rows_ = series.get(c["name"])
                if not rows_:
                    continue
                last = rows_[-1]
                ccy = "원" if c["market"] == "KR" else "달러"
                fmt_p = (lambda v: f"{v:,.0f}") if c["market"] == "KR" else (lambda v: f"{v:,.2f}")
                hi = max(r["high"] or r["close"] for r in rows_)
                lo = min(r["low"] or r["close"] for r in rows_)
                tr.append(f'<tr>{co_cell(c)}<td>{last["date"]}</td><td>{fmt_p(last["close"])} {ccy}</td>'
                          f'<td>{delta(prices.period_return(rows_), "%")}</td><td>{fmt_p(hi)}</td><td>{fmt_p(lo)}</td></tr>')
            show('<div class="scroll"><table class="grid"><thead><tr>' + th("회사", left=True) + th("기준일") + th("종가")
                 + th(f"{span} 수익률") + th("기간 최고") + th("기간 최저") + "</tr></thead><tbody>" + "".join(tr)
                 + "</tbody></table></div>")
        with st.container(border=True):
            names_px = [c["name"] for c in cos if c["name"] in series]
            who = st.selectbox("회사 선택", names_px, key="px_who")
            rows_ = series[who]
            cc = next(c for c in cos if c["name"] == who)
            f = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.74, 0.26], vertical_spacing=0.04)
            f.add_trace(go.Candlestick(
                x=[r["date"] for r in rows_], open=[r["open"] for r in rows_], high=[r["high"] for r in rows_],
                low=[r["low"] for r in rows_], close=[r["close"] for r in rows_], name=who,
                increasing=dict(line=dict(color="#d1263b", width=1), fillcolor="#d1263b"),
                decreasing=dict(line=dict(color="#1d5fd1", width=1), fillcolor="#1d5fd1")), row=1, col=1)
            up = [(r["close"] or 0) >= (r["open"] or 0) for r in rows_]
            f.add_trace(go.Bar(x=[r["date"] for r in rows_], y=[r["volume"] for r in rows_], name="거래량",
                               marker=dict(color=["#e9a3ac" if u else "#a3bde9" for u in up]),
                               hovertemplate="거래량 %{y:,.0f}<extra></extra>"), row=2, col=1)
            f.update_layout(showlegend=False, xaxis_rangeslider_visible=False, hovermode="x unified")
            style_fig(f, ",.0f" if cc["market"] == "KR" else ",.2f", height=460)
            f.update_xaxes(type="date")
            f.update_yaxes(tickformat=",.0f", row=2, col=1)
            st.plotly_chart(f, width="stretch", config=PCFG)
            st.caption("빨강은 상승(종가 ≥ 시가), 파랑은 하락입니다. 가격은 각 시장 통화(원·달러) 그대로입니다.")
    if KR_PX_KEY or US_PX_KEY:
        show(panel("주가 바로가기", link_tbl, "외부 시세 사이트로 연결합니다. 링크는 새 창에서 열립니다."))
        st.caption("국내 시세: 금융위원회 주식시세정보(공공데이터포털, 원천 한국거래소, 영업일 하루 뒤 공개). "
                   "미국 시세: Twelve Data 일봉. 수익률 비교는 통화와 관계없이 각 주가의 등락률입니다. "
                   "개인 분석용이며 데이터를 제3자에게 제공·재배포할 수 없습니다.")

with tab5:
    head = (th("회사", left=True) + th("통화") + th("항목", left=True) + th("계정 ID", left=True) + th("계정명", left=True)
            + "".join(th(str(y)) for y in reversed(YRS)) + th("공시 원문"))
    body = []
    for c in cos_annual:
        url = c["links"].get(year_annual)
        link = f'<a href="{e(url)}" target="_blank" rel="noopener">보기</a>' if url else "–"
        for m in dart.METRICS:
            acc = c["accounts"][m["key"]]
            body.append(
                f'<tr>{co_cell(c)}<td>{e(c["currency"])}</td><td class="l">{e(m["label"])}</td>'
                f'<td class="l flat">{e(acc["id"]) if acc else ""}</td><td class="l">{e(acc["nm"]) if acc else "(미확인)"}</td>'
                + "".join(f"<td>{n_won(c['years'][y]['amount'].get(m['key']))}</td>" for y in reversed(YRS))
                + f"<td>{link}</td></tr>")
    show(panel("", f'<table class="grid"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>',
               "공시 수치를 환율 변환 없이 각 회사의 보고 통화 그대로 표시합니다. 연간 실적(사업보고서) 기준이며, 공시 원문 링크는 기준연도 보고서입니다."))

show('<div class="foot">데이터 출처: 금융감독원 전자공시시스템(DART) 오픈API, 미국 증권거래위원회(SEC) EDGAR, '
     '환율은 유럽중앙은행 기준환율(Frankfurter API), 주가는 금융위원회 주식시세정보·Twelve Data.<br>'
     '업종과 회계 기준이 달라 수치만으로 기업의 우열을 단정할 수 없습니다. ROE와 ROA는 기말 잔액으로 단순 계산했습니다.</div>')
