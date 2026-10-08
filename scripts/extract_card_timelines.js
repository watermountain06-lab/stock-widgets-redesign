// 카드의 '시계열 주요 뉴스' 타임라인 항목을 꺼낸다(2026-10-08, 뉴스·영상 탭 '종목 소식' 칸).
// 이 저장소의 cards/ 사본(라이브에 올라간 카드)을 읽기만 한다.   node scripts/extract_card_timelines.js > out.json
// 반응 %는 카드 HTML에 적힌 값을 옮기지 않고, 카드 JS와 같은 식으로 그 카드의 DAILY에서 다시 계산한다
// (data-react 날짜 종가 ÷ 전날 종가 − 1, ±0.5% 미만은 flat — 카드가 화면에서 하는 계산 그대로).
const fs = require('fs'), path = require('path'), vm = require('vm');
const CARDS = path.join(__dirname, '..', 'cards');
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
const text = s => s.replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
const CATEGORY = { '': 'major', green: 'positive', red: 'negative', neutral: 'neutral' };
const out = {};
for (const f of fs.readdirSync(CARDS).filter(f => f.endsWith('_full_widget.html')).sort()) {
  const T = f.replace('_full_widget.html', '');
  const html = fs.readFileSync(path.join(CARDS, f), 'utf8');
  try {
    const daily = value(html, T, 'DAILY') || [];
    const ix = {}; daily.forEach((r, i) => { ix[r[0]] = i; });
    const start = html.indexOf('id="newsTimeline"');
    if (start < 0) { out[T] = { items: [] }; continue; }
    // 타임라인 구간 = newsTimeline부터 다음 섹션(class="section") 또는 첫 <script까지
    const ends = [html.indexOf('class="section"', start), html.indexOf('<script', start)].filter(x => x > 0);
    const region = html.slice(start, Math.min(...ends));
    const items = [];
    for (const m of region.matchAll(/<div class="tl-item">([\s\S]*?)(?=<div class="tl-item">|$)/g)) {
      const body = m[1];
      const dot = (body.match(/class="tl-dot\s*([a-z]*)"/) || [])[1];
      const dateHtml = (body.match(/<div class="tl-date">([\s\S]*?)<\/div>/) || [])[1];
      const title = (body.match(/<div class="tl-title">([\s\S]*?)<\/div>/) || [])[1];
      const src = body.match(/<a class="tl-source" href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/);
      const react = (body.match(/data-react="([\d-]+)"/) || [])[1];
      if (dot === undefined || !dateHtml || !title) throw new Error('timeline item without dot/date/title');
      let reaction = null, trend = null;
      const i = react ? ix[react] : undefined;
      if (i != null && i > 0) {
        const c = (daily[i][4] / daily[i - 1][4] - 1) * 100;
        reaction = Math.round(c * 10) / 10;
        trend = c >= 0.5 ? 'up' : c <= -0.5 ? 'down' : 'flat';   // 색은 반올림 전 값으로 — 카드와 같게(Codex)
      }
      items.push({ category: CATEGORY[dot] ?? 'neutral', heading: text(dateHtml.replace(/<span class="tl-reaction[\s\S]*?<\/span>/, '')),
                   title: text(title), url: src ? src[1] : null, source: src ? text(src[2]).replace(/\s*→$/, '') : null,
                   reactDate: react || null, reaction, trend });
    }
    out[T] = { items };
  } catch (e) { out[T] = { error: String(e).slice(0, 160) }; }
}
console.log(JSON.stringify(out, null, 1));
