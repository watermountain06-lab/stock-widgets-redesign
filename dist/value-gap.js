// 홈 "매수 기준가" 칸 (2026-10-07 시안, 10-08 '오늘의 발견' 왼쪽 hero 칸으로 이동).
// 값은 value-data.js(scripts/build_value_gap.py)에서 온다.
// 상승 여력·목표가는 보여주지 않는다 - 기준가는 사이트 규칙(현금흐름 '싸다' 경계)의 서술일 뿐이다.
(function(){
  var V = window.ValueGap, root = document.getElementById('value-gap');
  if (!root || !V) return;  // 데이터가 없으면 hero 칸은 원래처럼 비어 있다
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
  // 라벨은 가운데 정렬이라 막대 끝에서 잘리지 않게 안쪽으로 당긴다.
  function labelPos(p){ return Math.max(8, Math.min(92, p)); }
  function row(s){
    var r = s.price / s.buyPrice, pct = (s.gap * 100).toFixed(1);
    var gap = (s.gap <= 0 ? '−' : '+') + Math.abs(pct) + '%';
    var where = '기준가보다 ' + Math.abs(pct) + '% ' + (s.gap <= 0 ? '낮음' : '높음');
    var hard = s.hard.length
      ? '<span class="vg-hard" tabindex="0" title="' + esc(s.hard.map(function(k){ return HARD[k] || k; }).join(' · ')) + '">계산 주의</span>' : '';
    return '<li class="vg-row">'
      + '<a class="vg-name" href="' + esc(s.href) + '"><img src="logos/' + s.ticker.toLowerCase() + '.png" alt="" loading="lazy"><span><strong>' + esc(s.ticker) + hard + '</strong><small>' + esc(s.name) + '</small></span></a>'
      + '<div class="vg-gauge num" role="img" aria-label="현재가 ' + money(s.price) + ', 매수 기준가 ' + money(s.buyPrice) + ', ' + where + '">'
      +   '<span class="vg-gap' + (s.gap <= 0 ? ' is-under' : '') + '" style="left:' + labelPos(pos(r)) + '%">' + gap + '</span>'
      +   '<span class="vg-track"><span class="vg-zone" style="width:' + pos(1) + '%"></span><span class="vg-line" style="left:' + pos(1) + '%"></span>'
      +   '<span class="vg-dot' + (s.gap <= 0 ? ' is-under' : '') + '" style="left:' + pos(r) + '%" title="현재가 ' + money(s.price) + '"></span></span>'
      +   '<span class="vg-buy" style="left:' + labelPos(pos(1)) + '%" title="기본 내재가치의 90% · 현금흐름 판단이 \'싸다\'가 되는 가격">기준가 ' + money(Math.round(s.buyPrice)).replace(/\.00$/, '') + '</span>'
      + '</div>'
      + '</li>';
  }
  var list = V.stocks.length
    ? '<ul class="vg-list">' + V.stocks.map(row).join('') + '</ul>'
    : '<p class="vg-empty">오늘은 v2 판정이 적정~저평가 이상인 종목이 없습니다.</p>';
  // 관측 종목이 가장 많은 분기의 절반도 안 되는 분기(추적 시작 무렵)는 분모가 달라 뺀다.
  var fullest = Math.max.apply(null, V.history.map(function(h){ return h.total; }).concat([1]));
  var shown = V.history.filter(function(h){ return h.total >= fullest / 2; });
  var max = Math.max.apply(null, shown.map(function(h){ return h.under; }).concat([1]));
  var hist = shown.map(function(h, i){
    return '<li><button type="button" data-vg-quarter="' + i + '"' + (h.under ? '' : ' disabled') + ' aria-haspopup="dialog" aria-label="' + h.quarter + ' 기준가 아래 ' + h.under + '종목 (' + h.total + '종목 중)">'
      + '<span class="vg-bar" style="height:' + Math.round(h.under / max * 24) + 'px"></span><b>' + h.under + '</b><small>' + h.quarter.replace(/^20/, '').replace('Q', '.Q') + '</small></button></li>';
  }).join('');
  // 분기 막대를 누르면 '오늘의 발견'과 같은 대화상자에 그 분기의 종목을 보여 준다(대화상자는 index.html의 것을 같이 쓴다).
  function openQuarter(h){
    var dialog = document.getElementById('discovery-dialog');
    if (!dialog) return;
    var label = h.quarter.replace(/^(\d{4})Q(\d)$/, '$1년 $2분기');
    document.getElementById('discovery-title').textContent = label + ' 기준가 아래';
    document.getElementById('discovery-note').textContent = '그 분기 당시의 주가와, 그때까지의 공시로 계산한 기준가 기준 · 추적 ' + h.total + '종목 중';
    document.getElementById('discovery-position').textContent = h.under + '개 종목';
    document.getElementById('discovery-grid').innerHTML = h.stocks.map(function(s){
      return '<a class="discovery-card" href="cards/' + esc(s.ticker) + '_full_widget.html"><img src="logos/' + s.ticker.toLowerCase() + '.png" alt=""><span><strong>' + esc(s.ticker) + '</strong><small>' + esc(s.name) + '</small></span>'
        + '<span class="discovery-quote"><strong class="vg-dialog-gap">' + '−' + Math.abs(s.gap * 100).toFixed(1) + '%</strong></span>'
        + '<small class="selection-reason">' + s.date.replace(/-/g, '.') + ' · 당시 주가 ' + money(s.price) + ' · 기준가 ' + money(s.buyPrice) + '</small></a>';
    }).join('');
    dialog.showModal();
  }
  root.addEventListener('click', function(e){
    var b = e.target.closest('[data-vg-quarter]');
    if (b && !b.disabled) openQuarter(shown[Number(b.dataset.vgQuarter)]);
  });
  root.innerHTML = '<div class="vg-head"><p class="feature-kicker">VALUE CHECK</p><span class="vg-asof num">' + (V.asOf ? V.asOf.replace(/-/g, '.') + ' 종가' : '') + '</span></div>'
    + '<h2>매수 기준가와의 거리</h2>'
    + list
    + '<div class="vg-history"><p>분기별 기준가 아래 종목 수 <small>막대를 누르면 종목 보기</small></p><ol>' + hist + '</ol></div>';
})();
