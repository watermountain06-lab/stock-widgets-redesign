// 홈 "매수 기준가" 섹션 (2026-10-07 시안). 값은 value-data.js(scripts/build_value_gap.py)에서 온다.
// 상승 여력·목표가는 보여주지 않는다 - 기준가는 사이트 규칙(현금흐름 '싸다' 경계)의 서술일 뿐이다.
(function(){
  var V = window.ValueGap, root = document.getElementById('value-gap');
  if (!root) return;
  if (!V) { root.hidden = true; return; }
  var HARD = {
    roic: '자본수익률이 할인율 10%보다 낮아 성장이 가치를 만들지 못하는 구조',
    ic: '투하자본이 0 이하라 매출/자본이 상한에 걸림',
    tax: '실효세율이 10% 미만이라 세금 가정에 민감',
    nonop: '본업 밖 자산이 내재가치를 크게 좌우',
    nosol: '어떤 일정 성장률로도 현재가에 닿지 않음'
  };
  var LO = 0.6, HI = 1.4;  // 게이지 범위: 기준가의 0.6~1.4배
  function money(v){ return '$' + v.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}); }
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function pos(r){ return Math.max(0, Math.min(100, (r - LO) / (HI - LO) * 100)); }
  function vote(v){ return v == null ? '기권' : v > 0 ? '+' + v : v < 0 ? '−' + Math.abs(v) : '0'; }
  function row(s){
    var r = s.price / s.buyPrice, pct = Math.abs(s.gap * 100).toFixed(1);
    var where = s.gap <= 0 ? '기준가보다 ' + pct + '% 낮음' : '기준가보다 ' + pct + '% 높음';
    var judges = s.judges.map(function(j){
      return '<span class="vg-judge' + (j[1] > 0 ? ' is-plus' : j[1] < 0 ? ' is-minus' : '') + '">' + esc(j[0]) + ' ' + vote(j[1]) + '</span>';
    }).join('');
    var hard = s.hard.length
      ? '<span class="vg-hard" tabindex="0" title="' + esc(s.hard.map(function(k){ return HARD[k] || k; }).join(' · ')) + '">계산 주의</span>' : '';
    return '<li class="vg-row">'
      + '<a class="vg-name" href="' + esc(s.href) + '"><img src="logos/' + s.ticker.toLowerCase() + '.png" alt="" loading="lazy"><span><strong>' + esc(s.ticker) + '</strong><small>' + esc(s.name) + '</small></span></a>'
      + '<div class="vg-meta"><span class="vg-verdict">' + esc(s.verdict) + '</span>' + judges + hard + '</div>'
      + '<div class="vg-gauge" role="img" aria-label="현재가 ' + money(s.price) + ', 매수 기준가 ' + money(s.buyPrice) + ', ' + where + '">'
      +   '<span class="vg-zone" style="width:' + pos(1) + '%"></span><span class="vg-line" style="left:' + pos(1) + '%"></span>'
      +   '<span class="vg-dot' + (s.gap <= 0 ? ' is-under' : '') + '" style="left:' + pos(r) + '%"></span>'
      + '</div>'
      + '<div class="vg-text num"><b>' + where + '</b><small>현재가 ' + money(s.price) + ' · 기준가 ' + money(s.buyPrice) + '</small></div>'
      + '</li>';
  }
  var list = V.stocks.length
    ? '<ul class="vg-list">' + V.stocks.map(row).join('') + '</ul>'
    : '<p class="vg-empty">오늘은 v2 판정이 적정~저평가 이상인 종목이 없습니다.</p>';
  // 관측 종목이 가장 많은 분기의 절반도 안 되는 분기(추적 시작 무렵)는 분모가 달라 뺀다.
  var fullest = Math.max.apply(null, V.history.map(function(h){ return h.total; }).concat([1]));
  var shown = V.history.filter(function(h){ return h.total >= fullest / 2; });
  var max = Math.max.apply(null, shown.map(function(h){ return h.under; }).concat([1]));
  var hist = shown.map(function(h){
    return '<li title="' + h.quarter + ' · ' + h.total + '종목 중 ' + h.under + '종목"><span class="vg-bar" style="height:' + Math.round(h.under / max * 40) + 'px"></span><b>' + h.under + '</b><small>' + h.quarter.replace(/^20/, '').replace('Q', '.Q') + '</small></li>';
  }).join('');
  root.innerHTML = '<div class="vg-head"><div><p class="feature-kicker">VALUE CHECK</p><h2>매수 기준가와의 거리</h2>'
    + '<p class="vg-intro">v2 판정이 적정~저평가 이상인 종목만 보여 줍니다. 매수 기준가는 기본 내재가치의 90%로, 현금흐름 판단이 \'싸다\'가 되는 가격입니다.</p></div>'
    + '<span class="vg-asof num">' + (V.asOf ? V.asOf.replace(/-/g, '.') + ' 종가 기준' : '') + '</span></div>'
    + list
    + '<div class="vg-history"><p>분기별로 기준가 아래에 있던 종목 수 <small>(이 사이트 카드 약 80~90종목 중)</small></p><ol>' + hist + '</ol></div>'
    + '<p class="vg-note">기준가는 할인율 10%·영구성장률 2.5% 가정으로 계산한 값이라 목표가나 예상 수익률이 아닙니다. 판정은 사이트 규칙에 따른 결과이며, 이후 주가 수익을 뜻하지 않습니다. 카드는 손으로 고른 대형주라 시장 전체를 대표하지 않습니다.</p>';
})();
