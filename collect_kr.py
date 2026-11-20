"""피어스코프 국내 재무 데이터 수집기

DART(금융감독원 전자공시)는 해외 서버의 접속을 막고 있어서, 해외에 있는 Streamlit 서버는 DART에 직접 접속하지 못한다.
그래서 한국 PC에서 이 프로그램을 실행해 국내 상장사 전체의 최근 5개년 재무 수치를 파일 하나로 모아 두고,
그 파일(data/kr_financials.json.gz)을 GitHub에 올리면 앱이 그 파일을 읽는다.

실행: collect_kr.bat 더블클릭  (또는 명령창에서  python collect_kr.py)
- 중간에 멈춰도 다시 실행하면 이어서 수집한다.
- 1년에 한 번, 사업보고서가 다 나온 4월쯤 다시 실행하면 최신 데이터로 갱신된다.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

import dart

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "kr_financials.json.gz")
PART = os.path.join(HERE, "data", "_collect_progress.json")  # 이어받기용 (끝나면 지워짐)
# 인증키는 프로젝트 폴더가 아니라 사용자 폴더에 저장한다 → GitHub에 실수로 올라갈 일이 없음
KEY_FILE = os.path.join(os.path.expanduser("~"), ".peerscope_dart_key")
KST = timezone(timedelta(hours=9))
STOP_CODES = {"010": "등록되지 않은 인증키입니다", "011": "사용할 수 없는 인증키입니다",
              "012": "이 IP에서는 접근할 수 없는 인증키입니다", "020": "오늘 요청 한도를 넘었습니다. 내일 다시 실행하면 이어서 수집합니다",
              "800": "DART 시스템 점검 중입니다. 나중에 다시 실행하세요"}


class Stop(Exception):
    pass


def default_year(today: date | None = None) -> int:
    t = today or date.today()
    return t.year - 1 if t.month >= 5 else t.year - 2


def read_key(ask=input) -> str:
    if os.path.exists(KEY_FILE):
        k = open(KEY_FILE, encoding="utf-8").read().strip()
        if k:
            print("저장해 둔 DART 인증키를 사용합니다. (바꾸려면 python collect_kr.py --new-key)")
            return k
    k = ask("DART 인증키(40자리)를 붙여 넣고 Enter를 누르세요: ").strip().strip('"')
    if len(k) != 40 or not k.isalnum():
        raise Stop("인증키는 40자리 영문·숫자입니다. 다시 확인해 주세요.")
    if ask("다음 실행 때도 쓰도록 이 PC에 키를 저장할까요? (y/n): ").strip().lower() == "y":
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(k)
        print(f"저장했습니다: {KEY_FILE}")
    return k


def _save_json(path: str, obj: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def collect(key: str, year: int, http=requests, out: str = OUT, part: str = PART,
            pause: float = 0.3, log=print, max_companies: int | None = None) -> dict:
    log(f"[1/3] DART 상장사 목록을 받는 중… (기준 사업연도 {year})")
    try:
        corps = dart.listed(dart.fetch_corp_list(key, http=http))
    except dart.DartError as e:
        raise Stop(STOP_CODES.get(e.status, e.message)) from None
    corps = [{"code": c["code"], "name": c["name"], "stock": c["stock"]} for c in corps]
    if max_companies:
        corps = corps[:max_companies]

    state = {"base_year": year, "companies": {}}
    if os.path.exists(part):
        old = json.load(open(part, encoding="utf-8"))
        if old.get("base_year") == year:
            state = old
            log(f"      이전에 멈춘 곳부터 이어서 수집합니다. (완료 {len(state['companies'])}곳)")

    todo = [c for c in corps if c["code"] not in state["companies"]]
    log(f"[2/3] 재무제표 수집: 전체 {len(corps)}곳 중 남은 {len(todo)}곳")
    started, net_fail, ok_n = time.time(), 0, 0
    for i, c in enumerate(todo, 1):
        entry = None
        for attempt in range(3):
            try:
                entry = dart.cache_entry(dart.analyze_company(key, c, year, "CFS", http=http))
                net_fail = 0
                break
            except dart.DartError as e:
                if e.status == "013":
                    entry = {"status": "nodata"}
                    break
                if e.status in STOP_CODES:
                    _save_json(part, state)
                    raise Stop(STOP_CODES[e.status]) from None
                if e.status == "NET":
                    time.sleep(5 * (attempt + 1))
                    continue
                entry = {"status": "error", "message": f"{e.status}: {e.message}"}
                break
        if entry is None:  # 연결 실패 3번
            net_fail += 1
            if net_fail >= 3:
                _save_json(part, state)
                raise Stop("DART 연결이 계속 끊깁니다. 인터넷 연결을 확인하고 다시 실행하면 이어서 수집합니다.")
            continue
        state["companies"][c["code"]] = entry
        ok_n += entry["status"] == "ok"
        if i % 50 == 0 or i == len(todo):
            _save_json(part, state)
            rate = (time.time() - started) / i
            left = int(rate * (len(todo) - i) / 60)
            log(f"      {i}/{len(todo)}곳 완료 (예상 남은 시간 약 {left}분)")
        time.sleep(pause)

    log("[3/3] 파일로 저장하는 중…")
    data = {"version": 1, "base_year": year,
            "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
            "corps": corps, "companies": state["companies"]}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    if os.path.exists(part):
        os.remove(part)
    n_ok = sum(1 for v in data["companies"].values() if v.get("status") == "ok")
    log(f"완료! 재무 데이터 {n_ok}곳 / 전체 {len(corps)}곳 → {out}")
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="피어스코프 국내 재무 데이터 수집기")
    ap.add_argument("--year", type=int, default=default_year(), help="기준 사업연도 (기본: 최근 사업보고서 연도)")
    ap.add_argument("--new-key", action="store_true", help="저장된 인증키를 지우고 새로 입력")
    args = ap.parse_args(argv)
    print("=" * 56)
    print(" 피어스코프 국내 재무 데이터 수집기")
    print(" 국내 상장사 전체를 수집해서 시간이 꽤 걸립니다. 창을 닫지 마세요.")
    print("=" * 56)
    try:
        if args.new_key and os.path.exists(KEY_FILE):
            os.remove(KEY_FILE)
        key = read_key()
        collect(key, args.year)
        print("\n다음 단계: 이 폴더의 data 폴더 안 kr_financials.json.gz 파일을 GitHub 저장소에 올리세요.")
        return 0
    except Stop as e:
        print(f"\n멈춤: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n중단했습니다. 다시 실행하면 이어서 수집합니다.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
