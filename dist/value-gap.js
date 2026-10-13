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
    ? '<div class="vg-viewport"><ul class="vg-list">' + V.stocks.map(row).join('') + '</ul></div>'
    : '<p class="vg-empty">오늘은 v2 판정이 적정~저평가 이하인 종목이 없습니다.</p>';
  // 관측 종목이 가장 많은 분기의 절반도 안 되는 분기(추적 시작 무렵)는 분모가 달라 뺀다.
  var fullest = Math.max.apply(null, V.history.map(function(h){ return h.total; }).concat([1]));
  var shown = V.history.filter(function(h){ return h.total >= fullest / 2; });
  var max = Math.max.apply(null, shown.map(function(h){ return h.under; }).concat([1]));
  var hist = shown.map(function(h, i){
    return '<li><button type="button" data-vg-quarter="' + i + '"' + (h.under ? '' : ' disabled') + ' aria-haspopup="dialog" aria-label="' + h.quarter + ' 적정~저평가 이하 ' + h.under + '종목 (' + h.total + '종목 중)">'
      + '<span class="vg-bar" style="height:' + Math.round(h.under / max * 24) + 'px"></span><b>' + h.under + '</b><small>' + h.quarter.replace(/^20/, '').replace('Q', '.Q') + '</small></button></li>';
  }).join('');
  // 팝업 카드의 가로 막대(2026-10-13 시안): 뒤에 진입일에 유효했던 카드 예상밴드(반투명 초록, 점선), 앞에 그 밴드와
  // 같은 기간의 실제 최저~최고(노랑) - 밴드가 없는 카드는 노랑만, 그 분기 범위로. 진입가는 두 띠를 관통하는 세로선,
  // 현재가는 점. 진입가·현재가 라벨은 위, 실제 양 끝은 아래. 축은 카드마다 다르다(모든 값 + 4% 여백).
  function quarterBar(s){
    var b = s.band, aLo = b ? b.actualLow : s.low, aHi = b ? b.actualHigh : s.high;
    var vals = [aLo, aHi, s.entryPrice, s.current].concat(b ? [b.low, b.high] : []).filter(function(v){ return typeof v === 'number'; });
    var lo = Math.min.apply(null, vals) * 0.96, hi = Math.max.apply(null, vals) * 1.04;
    function x(v){ return ((v - lo) / (hi - lo) * 100).toFixed(1); }
    function lx(v){ return Math.max(14, Math.min(86, Number(x(v)))); }
    var day = ymd(s.entryDate);
    // 진입가와 현재가 라벨이 겹칠 만큼 가까우면 현재가를 한 줄 아래로.
    // (좁은 화면은 openQuarter가 실제 글자 폭으로 한 번 더 잰다.)
    var curRow = s.current != null && Math.abs(lx(s.entryPrice) - lx(s.current)) < 34 ? ' is-low' : '';
    var out = '<div class="vg-q" aria-label="' + (b ? '당시 예상밴드 ' + money(b.low) + '~' + money(b.high) + ', 같은 기간 실제 ' : '분기 주가 ')
      + money(aLo) + '~' + money(aHi) + ', ' + day + ' 진입가 ' + money(s.entryPrice) + ', 현재가 ' + (s.current != null ? money(s.current) : '없음') + '">';
    out += '<span class="vg-q-buy-label" style="left:' + lx(s.entryPrice) + '%">진입가 ' + money(s.entryPrice) + ' (' + day + ')</span>';
    if (s.current != null) out += '<span class="vg-q-cur-label' + curRow + '" data-row="' + (curRow ? 'low' : 'top') + '" style="left:' + lx(s.current) + '%">현재가 ' + money(s.current) + '</span>';
    out += '<span class="vg-q-track">';
    if (b) out += '<span class="vg-q-band" style="left:' + x(b.low) + '%;width:' + (x(b.high) - x(b.low)).toFixed(1) + '%"></span>';
    out += '<span class="vg-q-range" style="left:' + x(aLo) + '%;width:' + (x(aHi) - x(aLo)).toFixed(1) + '%"></span>';
    out += '<span class="vg-q-buy" style="left:' + x(s.entryPrice) + '%"></span>';
    if (s.current != null) out += '<span class="vg-q-cur" style="left:' + x(s.current) + '%"></span>';
    out += '</span>';
    out += '<span class="vg-q-end vg-q-low" style="left:' + x(aLo) + '%">' + money(aLo) + '</span>'
      + '<span class="vg-q-end vg-q-high" style="left:' + x(aHi) + '%">' + money(aHi) + '</span>';
    return out + '</div>';
  }
  // 팝업 날짜는 모두 YY/MM/DD 한 형식(2026-10-13 사용자).
  function ymd(v){ return v.slice(2).replace(/-/g, '/'); }
  // 막대 위 한 줄: 진입일에 유효했던 예상밴드와 노랑을 잰 기간.
  function bandInfo(s){
    var b = s.band;
    if (!b) return '<span class="vg-q-info">예상밴드 없음</span>';
    // 날짜는 노랑을 실제로 잰 기간이다. 아직 새 체크포인트가 없는 밴드는 카드의 최신 종가 날짜까지 쟀고, 예상 자체는
    // 다음 실적 반영까지 유효하다(ACN은 10/01 실적 뒤에도 10-K를 기다려 열려 있다 - Codex·Fable).
    return '<span class="vg-q-info"><b>예상 ' + money(b.low) + '~' + money(b.high) + '</b> (' + ymd(b.from) + '~' + ymd(b.to) + ')</span>';
  }
  // 진입가 대비 등락 한 줄: 왼쪽 라벨, 오른쪽 숫자. 색은 오르내림과 관계없이 줄마다 고정(분기 말 = 예상밴드 초록, 현재 = 본문색).
  // v가 문자열이면(분기 마지막 날 진입) 그대로 적는다. 반올림해 0.0%면 부호 없이('−0.0%' 방지).
  function stat(kind, label, v){
    var a = typeof v === 'number' ? Math.abs(v * 100).toFixed(1) : null;
    var text = a == null ? v : (a === '0.0' ? '' : v < 0 ? '−' : '+') + a + '%';
    return '<small>' + label + '</small><b class="vg-stat-' + kind + '">' + text + '</b>';
  }
  // 분기 막대를 누르면 '오늘의 발견'과 같은 대화상자에 그 분기의 종목을 보여 준다(대화상자는 index.html의 것을 같이 쓴다).
  function openQuarter(h){
    var dialog = document.getElementById('discovery-dialog');
    if (!dialog) return;
    var label = h.quarter.replace(/^(\d{4})Q(\d)$/, '$1년 $2분기');
    document.getElementById('discovery-title').textContent = label + ' 적정~저평가 이하' + (h.running ? ' (진행 중)' : '');
    // 설명 문장 없이 범례 한 줄만(2026-10-13 사용자: 글자 정리). '오늘의 발견'이 같은 대화상자를 열 때 textContent로 덮어 저절로 사라진다.
    document.getElementById('discovery-note').innerHTML = '<span class="vg-legend"><span><i class="vg-key-act"></i>실제 종가</span><span><i class="vg-key-band"></i>당시 예상 범위</span>'
      + '<span><i class="vg-key-entry"></i>진입가</span><span><i class="vg-key-cur"></i>현재가</span></span>';
    document.getElementById('discovery-position').textContent = h.under + '개 종목';
    document.getElementById('discovery-grid').innerHTML = h.stocks.map(function(s){
      // 끝난 분기인데 분기 말 등락이 없으면 그 분기 마지막 날에 들어온 것이다.
      var end = h.running ? '' : stat('end', '분기 말', s.endChange == null ? '진입' : s.endChange);
      var now = s.change == null ? '' : stat('now', '현재', s.change);
      return '<a class="discovery-card" href="cards/' + esc(s.ticker) + '_full_widget.html"><img src="logos/' + s.ticker.toLowerCase() + '.png" alt=""><span><strong>' + esc(s.ticker) + '</strong><small>' + esc(s.name) + '</small></span>'
        + '<span class="discovery-quote vg-stats">' + end + now + '</span>'
        + bandInfo(s) + quarterBar(s) + '</a>';
    }).join('');
    dialog.showModal();
    fitLabels(dialog);
  }
  // 최저·최고가는 띠 안쪽 끝에 맞춰 적고, 띠가 짧아 둘이 겹치면 바깥쪽으로 벌린다(칸 밖으로 나가면 다시 안쪽).
  // 팝업을 연 채 창 폭이 바뀌어도 다시 잰다(Codex) - 막대마다 처음 정한 줄(data-row)에서 다시 시작한다.
  function fitLabels(dialog){
    dialog.querySelectorAll('.vg-q').forEach(function(q){
      // 진입가·현재가 라벨이 실제로 겹치면(좁은 화면) 현재가를 한 줄 아래로(Codex).
      var bl = q.querySelector('.vg-q-buy-label'), cl = q.querySelector('.vg-q-cur-label');
      if (cl) cl.classList.toggle('is-low', cl.dataset.row === 'low');
      q.querySelectorAll('.vg-q-end').forEach(function(e){ e.classList.remove('is-out'); });
      // 라벨이 칸 밖으로 나가면(좁은 화면, 막대 끝 근처) 안쪽으로 민다.
      var qb = q.getBoundingClientRect();
      [bl, cl].forEach(function(l){
        if (!l) return;
        l.style.removeProperty('--nudge');
        var r = l.getBoundingClientRect();
        if (r.left < qb.left) l.style.setProperty('--nudge', (qb.left - r.left) + 'px');
        else if (r.right > qb.right) l.style.setProperty('--nudge', (qb.right - r.right) + 'px');
      });
      if (bl && cl && !cl.classList.contains('is-low')) {
        var r1 = bl.getBoundingClientRect(), r2 = cl.getBoundingClientRect();
        if (r1.right + 6 > r2.left && r2.right + 6 > r1.left) cl.classList.add('is-low');
      }
      var lo = q.querySelector('.vg-q-low'), hi = q.querySelector('.vg-q-high');
      if (!lo || !hi) return;
      var a = lo.getBoundingClientRect(), b = hi.getBoundingClientRect(), box = q.getBoundingClientRect();
      if (a.right + 4 <= b.left) return;
      lo.classList.add('is-out'); hi.classList.add('is-out');
      if (lo.getBoundingClientRect().left < box.left) lo.classList.remove('is-out');
      if (hi.getBoundingClientRect().right > box.right) hi.classList.remove('is-out');
    });
  }
  var qDialog = document.getElementById('discovery-dialog');
  if (qDialog && window.ResizeObserver) new ResizeObserver(function(){ if (qDialog.open && qDialog.querySelector('.vg-q')) fitLabels(qDialog); }).observe(qDialog);
  root.addEventListener('click', function(e){
    var b = e.target.closest('[data-vg-quarter]');
    if (b && !b.disabled) openQuarter(shown[Number(b.dataset.vgQuarter)]);
  });
  root.innerHTML = '<div class="vg-head"><p class="feature-kicker">VALUE CHECK</p><span class="vg-asof num">' + (V.asOf ? V.asOf.replace(/-/g, '.') + ' 종가' : '') + '</span></div>'
    + '<h2>매수 기준가와의 거리</h2>'
    + list
    + '<div class="vg-history"><p>분기별 적정~저평가 이하 종목 수 <small>막대를 누르면 종목 보기</small></p><ol>' + hist + '</ol></div>';

  // 종목이 VISIBLE개를 넘으면 시장 지표처럼 저절로 넘긴다 - 단, 세로로 한 줄씩 끊어서(2026-10-08 사용자 결정).
  // 1초마다(2026-10-08 사용자 요청, 처음엔 3.5초) 0.5초 동안 한 줄 올리고 맨 위 줄을 맨 아래로 옮긴다. 마우스·포커스가 있거나, 탭이 가려졌거나,
  // '동작 줄이기' 설정이면 멈춘다. 줄 높이는 칸 폭에 따라 바뀌므로(컨테이너 쿼리) 크기가 바뀔 때마다 다시 잰다.
  var VISIBLE = 4, STEP = 1000, SLIDE = 500;
  var viewport = root.querySelector('.vg-viewport'), ul = viewport && viewport.querySelector('.vg-list');
  if (!ul || ul.children.length <= VISIBLE) return;
  var reduced = matchMedia('(prefers-reduced-motion: reduce)'), paused = false, busy = false;
  function fit(){
    var rows = [].slice.call(ul.children, 0, VISIBLE);
    viewport.style.height = rows.reduce(function(h, li){ return h + li.offsetHeight; }, 0) + 'px';
  }
  function advance(){
    if (paused || busy || document.hidden || reduced.matches) return;
    busy = true;
    var first = ul.firstElementChild;
    ul.style.transition = 'transform ' + SLIDE + 'ms ease';
    ul.style.transform = 'translateY(-' + first.offsetHeight + 'px)';
    setTimeout(function(){
      ul.style.transition = 'none';
      ul.appendChild(first);
      ul.style.transform = 'none';
      busy = false;
    }, SLIDE);
  }
  viewport.addEventListener('mouseenter', function(){ paused = true; });
  viewport.addEventListener('mouseleave', function(){ paused = false; });
  viewport.addEventListener('focusin', function(){ paused = true; });
  viewport.addEventListener('focusout', function(){ paused = false; });
  if ('ResizeObserver' in window) new ResizeObserver(fit).observe(root); else addEventListener('resize', fit);
  fit();
  setInterval(advance, STEP);
})();
