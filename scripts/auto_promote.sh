#!/bin/bash
# preview → 라이브 자동 승격(2026-10-14 사용자 결정). .github/workflows/auto_promote.yml이 하루 한 번 부른다.
# 손 승격(README "라이브 승격 순서")과 같은 단계를 돌리고, 아래 경우에는 올리지 않고 실패로 끝낸다(GitHub이 메일로 알림):
#   - preview 마지막 실행이 안 끝났거나 실패한 카드가 있다, 실행·홈·카드 세션이 어긋난다, 라이브보다 오래됐다(auto_promote_gate.py)
#   - 승격 뒤 사이트 테스트가 실패한다
#   - 승격 단계가 정해진 파일 밖을 바꿨다
# 라이브에는 그날 시총 상위 100 종목만 올린다(2026-10-17 사용자 결정, scripts/live_set.py) — 상위 100에 든 preview
# 새 카드는 로고와 함께 자동으로 올라가고, 빠진 종목의 카드는 지운다(10-14의 '새 종목 건너뛰기'를 대신한다). 바뀐 것이 없으면 아무것도 하지 않고 끝난다. 멈춤 스위치는 워크플로의 저장소 변수 AUTO_PROMOTE(on일 때만 돈다).
#
#   bash scripts/auto_promote.sh            # 승격하고 커밋(푸시는 워크플로가)
#   DRY=1 bash scripts/auto_promote.sh      # 관문만 보고 쓰지 않는다
# preview 저장본은 ~/Workspace/stock-widgets-preview에 있어야 한다(승격 스크립트들이 그 경로를 읽는다).
set -e -o pipefail
cd "$(dirname "$0")/.."
PV="$HOME/Workspace/stock-widgets-preview"
[ -d "$PV" ] || { echo "preview 저장본 없음: $PV"; exit 2; }
# ETF(2026-10-21): 실패는 카드 승격을 막지 않는다 — 사유를 이 파일에 남기고 워크플로 "ETF status" 단계가 메일로 알린다.
ETF_STATUS="${RUNNER_TEMP:-/tmp}/etf_status"; rm -f "$ETF_STATUS"

# 관문 1: preview 실행이 끝났고 실패 카드가 없으며, 실행·홈·카드의 세션이 같고 라이브보다 오래되지 않았다(scripts/auto_promote_gate.py)
# preview가 아직 갱신 중이면(관문 종료 코드 3) 15분마다 preview를 다시 받아 최대 3시간 기다린다(2026-10-15 사용자 결정).
# 실패 카드처럼 기다려도 안 풀리는 이유(코드 1)는 바로 멈춘다. DRY는 기다리지 않는다.
TRIES=12; [ -n "$DRY" ] && TRIES=0
for i in $(seq 0 "$TRIES"); do
  rc=0; python3 scripts/auto_promote_gate.py || rc=$?
  [ "$rc" = 0 ] && break
  if [ "$rc" != 3 ] || [ "$i" = "$TRIES" ]; then exit 1; fi
  echo "15분 뒤 다시 본다 ($((i + 1))/$TRIES)"; sleep 900
  git -C "$PV" pull -q --ff-only || echo "preview 받기 실패 — 15분 뒤 다시"   # 한 번의 네트워크 오류로 기다린 시간을 버리지 않는다(Fable)
done
SESSION=$(python3 -c "import json;print(json.load(open('$PV/v2/daily_status.json')).get('session',''))")

# ETF 후보(scripts/sync_etf.py): preview 작업 트리는 그대로 두고(카드·SESSION은 관문 1이 본 그대로), ETF 입력만 고를 커밋을 정한다.
# origin/main → HEAD 순으로 "입력 검증 통과 + 홈 세션에 값을 보임"인 첫 커밋. 없으면 5분마다 최대 4번(20분) 다시, 끝내 없으면
# 검증만 통과한 가장 새 커밋, 그것도 없으면 HEAD(→ 입력 거부: 기존 라이브 묶음의 링크만 다시 맞춤). 유출 검사기도 그 커밋 것 하나로 고정.
etf_pick() {   # $1 = 기다릴 횟수. 표준 출력은 고른 커밋 하나뿐(나머지는 표준 오류)
  local tries=$1 i c out rc fallback="" first cands
  for i in $(seq 0 "$tries"); do
    if git -C "$PV" fetch -q origin 2>/dev/null; then
      cands="$(git -C "$PV" rev-parse -q --verify origin/main 2>/dev/null) $(git -C "$PV" rev-parse HEAD)"
    else
      echo "WARN preview fetch 실패 — 기다리지 않고 HEAD만 본다" >&2
      cands=$(git -C "$PV" rev-parse HEAD); tries=$i
    fi
    first=""
    for c in $cands; do
      rc=0; out=$(python3 scripts/sync_etf.py --check --rev "$c" --session "$SESSION" 2>&1) || rc=$?
      if [ "$rc" = 0 ] || [ "$rc" = 1 ]; then
        if printf '%s' "$out" | grep -q 'session_ok=1'; then echo "$c"; return 0; fi
        [ -z "$first" ] && first=$c   # 이번 회차에서 검증을 통과한 가장 새 후보
      fi
    done
    [ -n "$first" ] && fallback=$first   # 가장 최근 회차의 것으로 갱신
    [ "$i" -ge "$tries" ] && break
    echo "ETF가 아직 홈 세션 $SESSION 것이 아니다 — 5분 뒤 다시 ($((i + 1))/$tries)" >&2; sleep 300
  done
  echo "${fallback:-$(git -C "$PV" rev-parse HEAD)}"
}

# 상위 100 기준으로 무엇이 들어오고 빠지는지 찍는다
CHECK=$(python3 scripts/sync_cards.py --check || true)   # --check는 뒤처졌으면 0이 아닌 값으로 끝난다
printf '%s\n' "$CHECK" | grep -E '^(would (add|update|remove|copy logo)|not in the top 100)' | cut -c1-200 || true   # head는 파이프를 먼저 닫아 pipefail로 멈춘다

if [ -n "$DRY" ]; then
  ETF_REV=$(etf_pick 0); rc=0; python3 scripts/sync_etf.py --check --rev "$ETF_REV" --session "$SESSION" | cut -c1-300 || rc=$?
  echo "DRY: 관문 통과 — 쓰지 않음(ETF 확인 종료 코드 $rc)"; exit 0
fi
ETF_REV=$(etf_pick 4)
[ -n "$ETF_REV" ] || { echo "멈춤: ETF 후보 선택 실패"; exit 1; }
LEAK_CHECKER="${RUNNER_TEMP:-/tmp}/check_live_leak_pinned.py"
git -C "$PV" show "$ETF_REV:pipeline/site_ui/check_live_leak.py" > "$LEAK_CHECKER"
export LEAK_CHECKER

# 승격(README 순서 1~9; 3번 로고는 sync_cards가 새로 든 종목의 로고를 preview에서 복사한다)
python3 scripts/sync_cards.py | cut -c1-200
python3 scripts/fix_backbar_chain.py --cards-dir "$PWD/cards" | tail -1
# ETF 파일: 카드 집합이 정해진 뒤(링크를 오늘 상위 100에 맞춘다). 4 = 입력 거부(기존 묶음 링크만) → 표시 파일에 바로 남기고 계속,
# 5(기존 묶음도 없음·검사기 옛 버전)·2(오류)는 카드 승격도 멈춘다.
ETF_RC=0; ETF_OUT=$(python3 scripts/sync_etf.py --rev "$ETF_REV" --session "$SESSION" 2>&1) || ETF_RC=$?
printf '%s\n' "$ETF_OUT" | cut -c1-300
if [ "$ETF_RC" = 4 ]; then printf 'ETF 입력 거부(preview %s): %s\n' "$ETF_REV" "$ETF_OUT" > "$ETF_STATUS"
elif [ "$ETF_RC" != 0 ]; then echo "멈춤: sync_etf 종료 코드 $ETF_RC"; exit 1; fi
ETF_FILES=$(python3 -c "import sys; sys.path.insert(0,'scripts'); import sync_etf as s; o,_=s.read_order(__import__('pathlib').Path('.')); print(' '.join(['etf-data.js']+['etf-%s.html'%t.lower() for t in o]))")

# 바뀐 것이 없으면 끝 — 카드는 순위 링크를 다시 맞춘 뒤에 비교한다. preview의 마지막 라이브 카드는 '다음'이
# 아직 안 올린 새 종목을 가리켜, 복사 전 비교로는 매일 바뀐 것처럼 보인다(Fable)
CHANGED=0
if [ -n "$(git status --porcelain cards logos $ETF_FILES)" ]; then CHANGED=1; fi
python3 scripts/build_home.py --check >/dev/null 2>&1 || CHANGED=1
if [ "$CHANGED" = 0 ]; then echo "preview와 같다 — 할 일 없음"; exit 0; fi
python3 scripts/build_home.py | tail -1
python3 scripts/build_value_gap.py | tail -1
python3 scripts/build_stock_news.py | tail -1
python3 scripts/build_tracking.py | tail -1
python3 tooling/build_static.py | tail -1
python3 -m unittest discover -s tooling 2>&1 | tail -3
python3 "$LEAK_CHECKER" "$PWD" | tail -1   # 유출은 카드 승격도 멈춘다(set -e)

# 관문 3: 정해진 파일 밖을 바꾸지 않았는지
ETF_RE=$(printf '%s\n' $ETF_FILES | sed 's/\./\\./g' | paste -sd'|' -)
OTHER=$(git status --porcelain | awk '{print $2}' | grep -vE "^(cards/|logos/|dist/|stock-data\.js$|value-data\.js$|stock-news\.js$|tracking-data\.js$|($ETF_RE)$)" || true)
if [ -n "$OTHER" ]; then echo "멈춤: 승격 단계가 정해진 파일 밖을 바꿨다 — $OTHER"; exit 1; fi

git add -A cards logos dist && git add stock-data.js value-data.js stock-news.js tracking-data.js $ETF_FILES
if git diff --cached --quiet; then echo "변경 없음"; exit 0; fi
git commit -q -m "Auto-promote preview session $SESSION"
echo "커밋: $(git log --oneline -1)"
