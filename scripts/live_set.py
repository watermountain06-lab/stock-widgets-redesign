"""자동 승격이 새 종목을 건너뛸 때 쓰는 라이브 종목 목록(2026-10-14 사용자 결정).

scripts/auto_promote.sh가 PROMOTE_SKIP_NEW=1을 켜면 승격 단계들이 이 저장소 cards/에 이미 있는 종목만 다룬다 —
preview에서 만들고 있는 새 카드는 로고·홈 순위를 확인한 뒤 손으로 승격할 때까지 라이브에 나오지 않는다.
켜지 않으면(손 승격) None을 돌려주고, 각 단계는 예전처럼 preview 전체를 다룬다.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def live_tickers():
    if os.environ.get("PROMOTE_SKIP_NEW") != "1":
        return None
    return {p.name.replace("_full_widget.html", "") for p in (REPO / "cards").glob("*_full_widget.html")}
