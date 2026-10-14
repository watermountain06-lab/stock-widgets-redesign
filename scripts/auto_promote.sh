#!/bin/bash
# preview → 라이브 자동 승격(2026-10-14 사용자 결정). .github/workflows/auto_promote.yml이 하루 한 번 부른다.
# 손 승격(README "라이브 승격 순서")과 같은 단계를 돌리고, 아래 경우에는 올리지 않고 실패로 끝낸다(GitHub이 메일로 알림):
#   - preview 마지막 실행이 안 끝났거나 실패한 카드가 있다, 실행·홈·카드 세션이 어긋난다, 라이브보다 오래됐다(auto_promote_gate.py)
#   - preview에 이 저장소에 없는 새 종목 카드가 있다(로고·홈 순위 확인이 필요 — 손으로 승격)
#   - 승격 뒤 사이트 테스트가 실패한다
#   - 승격 단계가 정해진 파일 밖을 바꿨다
# 바뀐 것이 없으면 아무것도 하지 않고 끝난다. 멈춤 스위치는 워크플로의 저장소 변수 AUTO_PROMOTE(on일 때만 돈다).
#
#   bash scripts/auto_promote.sh            # 승격하고 커밋(푸시는 워크플로가)
#   DRY=1 bash scripts/auto_promote.sh      # 관문만 보고 쓰지 않는다
# preview 저장본은 ~/Workspace/stock-widgets-preview에 있어야 한다(승격 스크립트들이 그 경로를 읽는다).
set -e -o pipefail
cd "$(dirname "$0")/.."
PV="$HOME/Workspace/stock-widgets-preview"
[ -d "$PV" ] || { echo "preview 저장본 없음: $PV"; exit 2; }

# 관문 1: preview 실행이 끝났고 실패 카드가 없으며, 실행·홈·카드의 세션이 같고 라이브보다 오래되지 않았다(scripts/auto_promote_gate.py)
python3 scripts/auto_promote_gate.py
SESSION=$(python3 -c "import json;print(json.load(open('$PV/v2/daily_status.json')).get('session',''))")

# 관문 2: 새 종목(이 저장소에 카드가 없는 preview 카드)
CHECK=$(python3 scripts/sync_cards.py --check || true)   # --check는 뒤처졌으면 0이 아닌 값으로 끝난다
printf '%s\n' "$CHECK" | sed -n '1,2p' | cut -c1-200   # head는 파이프를 먼저 닫아 pipefail로 멈춘다
NEW=$(echo "$CHECK" | sed -n 's/^would add [0-9]*: //p')
if [ -n "$NEW" ] && [ "$NEW" != "-" ]; then echo "멈춤: 새 종목 $NEW — 로고·홈 순위를 확인하고 손으로 승격한다"; exit 1; fi

# 바뀐 것이 없으면 끝
CHANGED=0
printf '%s\n' "$CHECK" | grep -q "^would update 0:" || CHANGED=1
python3 scripts/build_home.py --check >/dev/null 2>&1 || CHANGED=1
if [ "$CHANGED" = 0 ]; then echo "preview와 같다 — 할 일 없음"; exit 0; fi
if [ -n "$DRY" ]; then echo "DRY: 관문 통과, 승격할 변경 있음 — 쓰지 않음"; exit 0; fi

# 승격(README 순서 1·2·4~9; 3번 로고는 새 종목이 없으므로 건너뛴다)
python3 scripts/sync_cards.py | cut -c1-200
python3 scripts/fix_backbar_chain.py --cards-dir "$PWD/cards" | tail -1
python3 scripts/build_home.py | tail -1
python3 scripts/build_value_gap.py | tail -1
python3 scripts/build_stock_news.py | tail -1
python3 scripts/build_tracking.py | tail -1
python3 tooling/build_static.py | tail -1
python3 -m unittest discover -s tooling 2>&1 | tail -3

# 관문 3: 정해진 파일 밖을 바꾸지 않았는지
OTHER=$(git status --porcelain | awk '{print $2}' | grep -vE '^(cards/|dist/|stock-data\.js|value-data\.js|stock-news\.js|tracking-data\.js)' || true)
if [ -n "$OTHER" ]; then echo "멈춤: 승격 단계가 정해진 파일 밖을 바꿨다 — $OTHER"; exit 1; fi

git add cards dist stock-data.js value-data.js stock-news.js tracking-data.js
if git diff --cached --quiet; then echo "변경 없음"; exit 0; fi
git commit -q -m "Auto-promote preview session $SESSION"
echo "커밋: $(git log --oneline -1)"
