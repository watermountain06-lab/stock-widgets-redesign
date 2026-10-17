"""라이브에 올리는 종목 목록 — preview 전체 중 그날 시가총액 상위 100(2026-10-17 사용자 결정).

preview(~/Workspace/stock-widgets-preview)는 카드를 계속 늘리지만, 라이브는 그날 시총 상위 TOP_N 종목만 보여 주고
자동 갱신한다. 승격 단계(sync_cards·build_home·build_value_gap·build_tracking·auto_promote_gate)가 모두 이 목록을 쓴다:
목록 밖 종목은 홈·카드·매수 기준가·Tracking 어디에도 나오지 않고, sync_cards가 이 저장소 cards/에서 지운다.
순위는 preview 홈 DATA의 marketCap(종가 × 주식 수) 순, 같으면 티커 순 — build_home.preview_data의 순위와 같다.
멤버는 매일 바뀔 수 있다: 경계 근처 종목은 들어왔다 빠졌다 하고, preview의 새 카드도 상위 TOP_N에 들면 로고와 함께
자동으로 올라간다(이전의 '새 종목은 손 승격'(2026-10-14, PROMOTE_SKIP_NEW)을 대신한다).
"""
import json
from pathlib import Path

TOP_N = 100
PREVIEW_HOME = Path.home() / "Workspace/stock-widgets-preview/index.html"


def live_tickers():
    src = PREVIEW_HOME.read_text(encoding="utf-8")
    try:
        a = src.index("var DATA = [")
        b = src.index("\n  ];", a)
        rows = json.loads(src[a + len("var DATA = "): b + len("\n  ]")])
    except ValueError as e:
        raise SystemExit(f"live_set: cannot read DATA from {PREVIEW_HOME}: {e}") from e
    if any(not isinstance(r.get("marketCap"), (int, float)) or r["marketCap"] <= 0 for r in rows):
        raise SystemExit("live_set: a preview row has no positive marketCap - cannot pick the top 100")
    rows.sort(key=lambda r: (-r["marketCap"], r["ticker"]))
    return {r["ticker"] for r in rows[:TOP_N]}
