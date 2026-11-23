"""피어스코프를 내 PC에서 실행한다 (주가 탭 포함, 개인 분석용).

주가 데이터(한국거래소·Twelve Data)는 이용 조건상 공개 웹사이트에 띄울 수 없어서,
공개 배포(Streamlit)에서는 주가 탭이 꺼져 있고 내 PC에서 실행할 때만 켜진다.
키는 프로젝트 폴더가 아니라 윈도우 사용자 폴더의 .streamlit/secrets.toml 에 저장돼 GitHub에 올라가지 않는다.

실행: run_app.bat 더블클릭  (키를 다시 입력하려면  python run_local.py --keys)
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.join(os.path.expanduser("~"), ".streamlit", "secrets.toml")


def toml_str(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_keys(ask=input, path: str = SECRETS) -> None:
    print("처음 한 번만 키를 입력합니다. 없는 키는 그냥 Enter를 누르세요.")
    vals = {
        "DATA_GO_KR_KEY": ask("공공데이터포털 일반 인증키 (국내 주가): ").strip().strip('"'),
        "TWELVE_DATA_KEY": ask("Twelve Data API 키 (미국 주가): ").strip().strip('"'),
        "SEC_USER_AGENT": ask("SEC 접속용 이름과 이메일 (예: Jimin Kim abc@example.com): ").strip().strip('"'),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for k, v in vals.items():
            if v:
                f.write(f"{k} = {toml_str(v)}\n")
    print(f"저장했습니다: {path}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--keys" in argv or not os.path.exists(SECRETS):
        write_keys()
    print("\n피어스코프를 여는 중입니다. 잠시 뒤 브라우저가 열립니다. 끝내려면 이 창을 닫으세요.\n")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", os.path.join(HERE, "app.py")])


if __name__ == "__main__":
    sys.exit(main())
