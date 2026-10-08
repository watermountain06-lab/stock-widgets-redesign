// 카드의 '예상밴드 백테스트' 현재 밴드를 꺼낸다(2026-10-08, 홈 '평가 · 밴드 위치' 칸).
// preview v2 카드를 읽기만 한다. 카드마다 데이터 형식이 JSON이거나 JS 객체라 node에서 그대로 평가한다.
//   node scripts/extract_card_bands.js > out.json
// 결과: {T: {low, high, checkpoint, close, date, perNA}} — 밴드가 없으면 low·high가 null.
const fs = require('fs'), path = require('path'), os = require('os'), vm = require('vm');
const V2 = path.join(os.homedir(), 'Workspace/stock-widgets-preview/v2');
function block(src, start) {            // preview v2/research/extract_card_verdicts.js와 같은 짝 맞추기
  let depth = 0, i = start, q = null;
  for (; i < src.length; i++) {
    const c = src[i];
    if (q) { if (c === '\\') { i++; continue; } if (c === q) q = null; continue; }
    if (c === '"' || c === "'" || c === '`') { q = c; continue; }
    if (c === '/' && src[i + 1] === '/') { i = src.indexOf('\n', i); continue; }
    if (c === '/' && src[i + 1] === '*') { i = src.indexOf('*/', i) + 1; continue; }
    if (c === '{' || c === '(' || c === '[') depth++;
    if (c === '}' || c === ')' || c === ']') { depth--; if (depth === 0) return i + 1; }
  }
  return -1;
}
function value(html, T, name) {
  const m = html.indexOf(`const ${T}_${name} =`);
  if (m < 0) return undefined;
  let k = html.indexOf('=', m) + 1;
  while (/\s/.test(html[k])) k++;
  return vm.runInNewContext('(' + html.slice(k, block(html, k)) + ')', {}, { timeout: 1000 });
}
const out = {};
for (const f of fs.readdirSync(V2).filter(f => f.endsWith('_full_widget.html')).sort()) {
  const T = f.replace('_full_widget.html', '');
  const html = fs.readFileSync(path.join(V2, f), 'utf8');
  try {
    const bt = value(html, T, 'BACKTEST') || [], daily = value(html, T, 'DAILY') || [];
    const val = value(html, T, 'VALUATION') || {};
    // 진행 중인 체크포인트(마지막 실적 발표일에 정한 밴드, 다음 발표까지 고정)만 쓴다
    const cp = bt.length && bt[bt.length - 1].is_open ? bt[bt.length - 1] : null;
    const last = daily[daily.length - 1] || [];
    out[T] = { low: cp ? cp.predicted_low : null, high: cp ? cp.predicted_high : null,
               checkpoint: cp ? cp.checkpoint_date : null, close: last[4] ?? null, date: last[0] ?? null,
               perNA: !!val.perNA };
  } catch (e) { out[T] = { error: String(e).slice(0, 120) }; }
}
console.log(JSON.stringify(out, null, 1));
