"""주가(일별 시세).

- 국내: 공공데이터포털 '금융위원회_주식시세정보' (영업일 하루 뒤 공개되는 일별 시세, 2020년 이후)
- 미국: Twelve Data time_series (무료 Basic 요금제: 미국 주식, 하루 800회·분당 8회)
결과는 [{"date": "YYYY-MM-DD", "open", "high", "low", "close", "volume"}] 날짜순.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

# 공식 활용가이드(V2) 기준 주소
KR_API = "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2"
US_API = "https://api.twelvedata.com/time_series"
TIMEOUT = (10, 30)


class PriceError(Exception):
    pass


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def kr_prices(service_key: str, stock_code: str, start: date, end: date, http=requests) -> list[dict]:
    rows, page = [], 1
    while True:
        try:
            res = http.get(KR_API, params={
                "serviceKey": service_key, "resultType": "json", "numOfRows": 1000, "pageNo": page,
                "likeSrtnCd": stock_code, "beginBasDt": start.strftime("%Y%m%d"),
                # endBasDt 는 '보다 작은' 날짜만 찾으므로 하루 뒤로 넣어야 끝날이 포함된다
                "endBasDt": (end + timedelta(days=1)).strftime("%Y%m%d")}, timeout=TIMEOUT)
        except requests.RequestException:
            raise PriceError("공공데이터포털 시세 서버에 연결하지 못했습니다. 해외 서버의 접속이 막혀 있을 수 있습니다.") from None
        text = getattr(res, "text", "") or ""
        # 공식 가이드의 오류 메시지 (본문이 JSON이 아닐 수 있어 글자로 먼저 확인)
        for sign, msg in (("Unauthorized", "공공데이터포털 인증키가 없거나 올바르지 않습니다."),
                          ("SERVICE_KEY_IS_NOT_REGISTERED", "공공데이터포털 인증키가 아직 등록되지 않았습니다. 잠시 후 다시 시도하세요."),
                          ("Forbidden", "주식시세정보 활용신청 내역이 확인되지 않습니다. 신청·승인 상태를 확인하세요."),
                          ("API token quota exceeded", "공공데이터포털 하루 호출 한도를 넘었습니다. 내일 다시 시도하세요."),
                          ("API rate limit exceeded", "공공데이터포털 요청이 몰려 있습니다. 잠시 후 다시 시도하세요."),
                          ("API not found", "공공데이터포털 API 주소가 바뀌었습니다.")):
            if sign in text[:500]:
                raise PriceError(msg)
        try:
            j = res.json()
        except ValueError:
            raise PriceError(f"공공데이터포털 응답을 읽지 못했습니다 (HTTP {res.status_code}).") from None
        resp = j.get("response", {})
        head = resp.get("header", {})
        if str(head.get("resultCode", "00")) not in ("00", "0"):
            raise PriceError(f"공공데이터포털 오류: {head.get('resultMsg', '')}")
        body = resp.get("body", {})
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        for it in items:
            if str(it.get("srtnCd", "")).strip() != stock_code:
                continue  # likeSrtnCd 는 '포함' 검색이라 다른 종목이 섞일 수 있음
            d = str(it.get("basDt", ""))
            rows.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "open": _num(it.get("mkp")), "high": _num(it.get("hipr")),
                         "low": _num(it.get("lopr")), "close": _num(it.get("clpr")), "volume": _num(it.get("trqu"))})
        total = int(body.get("totalCount") or 0)
        if page * 1000 >= total or not items:
            break
        page += 1
    if not rows:
        raise PriceError("해당 기간의 시세가 없습니다.")
    return sorted({r["date"]: r for r in rows}.values(), key=lambda r: r["date"])


def us_prices(api_key: str, symbol: str, start: date, end: date, http=requests) -> list[dict]:
    try:
        res = http.get(US_API, params={"symbol": symbol, "interval": "1day", "start_date": start.isoformat(),
                                       "end_date": end.isoformat(), "outputsize": 5000, "apikey": api_key},
                       timeout=TIMEOUT)
        j = res.json()
    except requests.RequestException:
        raise PriceError("Twelve Data 서버에 연결하지 못했습니다.") from None
    except ValueError:
        raise PriceError("Twelve Data 응답을 읽지 못했습니다.") from None
    if j.get("status") == "error":
        code = j.get("code")
        if code == 429:
            raise PriceError("Twelve Data 무료 요청 한도(분당 8회·하루 800회)를 넘었습니다. 잠시 후 다시 시도하세요.")
        if code in (401, 403):
            raise PriceError("Twelve Data API 키가 올바르지 않거나, 무료 요금제에서 볼 수 없는 종목입니다.")
        raise PriceError(f"Twelve Data 오류: {j.get('message', '')}")
    rows = [{"date": v["datetime"][:10], "open": _num(v.get("open")), "high": _num(v.get("high")),
             "low": _num(v.get("low")), "close": _num(v.get("close")), "volume": _num(v.get("volume"))}
            for v in j.get("values", [])]
    if not rows:
        raise PriceError("해당 기간의 시세가 없습니다.")
    return sorted(rows, key=lambda r: r["date"])


def period_return(rows: list[dict]):
    c = [r["close"] for r in rows if r["close"]]
    return None if len(c) < 2 else c[-1] / c[0] - 1
