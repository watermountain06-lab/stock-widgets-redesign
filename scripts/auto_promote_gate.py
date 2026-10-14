#!/usr/bin/env python3
"""자동 승격 관문(scripts/auto_promote.sh가 부른다, 2026-10-14). 통과하면 0, 아니면 이유를 찍고 1.

- preview 마지막 실행이 끝났고(started ≤ finished) 실패 카드가 없다
- 그 실행의 세션 = preview 홈 시세 세션(priceSession) = 모든 카드의 마지막 종가일 — 실행 중이거나 일부만 갱신된 preview를 올리지 않는다(Codex)
- preview 세션이 라이브 세션보다 앞서거나 같다 — 오래된 preview로 라이브를 되돌리지 않는다(Codex)
"""
import json
import re
import sys
from pathlib import Path

PV = Path.home() / "Workspace/stock-widgets-preview"
LIVE = Path(__file__).resolve().parents[1] / "stock-data.js"
st = json.loads((PV / "v2/daily_status.json").read_text(encoding="utf-8"))
why = []
if not st.get("finished") or not st.get("started") or st["finished"] < st["started"]:
    why.append(f"preview 실행이 끝나지 않았다(started {st.get('started')}, finished {st.get('finished')})")
if st.get("failed"):
    why.append(f"preview에 실패한 카드: {' '.join(st['failed'])}")
ps = sorted(set(re.findall(r'priceSession"\s*:\s*"(\d{4}-\d{2}-\d{2})"', (PV / "index.html").read_text(encoding="utf-8"))))
ls = sorted(set(re.findall(r'priceSession"\s*:\s*"(\d{4}-\d{2}-\d{2})"', LIVE.read_text(encoding="utf-8")))) if LIVE.exists() else []
if len(ps) != 1:
    why.append(f"preview 홈 시세 세션이 하나가 아니다: {ps}")
else:
    ps = ps[0]
    if st.get("session") != ps:
        why.append(f"preview 실행 세션 {st.get('session')} ≠ 홈 시세 세션 {ps}")
    lag = []
    for f in sorted(PV.glob("*_full_widget.html")):
        t = f.name.replace("_full_widget.html", "")
        m = re.search(r"const " + re.escape(t) + r"_DAILY = \[.*?\[\"(\d{4}-\d{2}-\d{2})\"[^\[\]]*\]\];", f.read_text(encoding="utf-8"), re.S)
        if not m or m.group(1) != ps:
            lag.append(f"{t}({m.group(1) if m else '없음'})")
    if lag:
        why.append(f"마지막 종가가 {ps}가 아닌 카드 {len(lag)}장: {' '.join(lag[:10])}")
    if ls and ps < max(ls):
        why.append(f"preview 세션 {ps}가 라이브 {max(ls)}보다 오래됐다 — 되돌리지 않는다")
if why:
    print("멈춤: " + " / ".join(why))
    sys.exit(1)
print(f"관문 통과: preview 세션 {ps}(라이브 {max(ls) if ls else '없음'})")
