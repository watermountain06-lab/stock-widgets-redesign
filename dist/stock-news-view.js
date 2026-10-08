// 뉴스·영상 탭 "종목 소식" 칸 (2026-10-08 시안). 값은 stock-news.js(scripts/build_stock_news.py)에서 온다 —
// 카드 타임라인 항목을 날짜별로 모은 것뿐이라 새 사건이나 요약을 만들지 않는다.
// 처음엔 최근 5건만 보이고, '이전 소식 더 보기'를 누를 때마다 5건씩 더 편다(2026-10-08 사용자 결정 — 90일은 너무 길었다).
(function(){
  var N = window.StockNews, root = document.getElementById('stock-news-list');
  if (!root || !N || !N.items.length) return;
  var STEP = 5, LABEL = {major:'초대형 이벤트', positive:'긍정', negative:'부정', neutral:'중립'};
  var shown = STEP;
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function day(d){ var t = new Date(d + 'T00:00:00'); return t.getFullYear() + '년 ' + (t.getMonth()+1) + '월 ' + t.getDate() + '일 (' + '일월화수목금토'[t.getDay()] + ')'; }
  function react(r, trend){
    if (r == null) return '';
    var t = Math.abs(r).toFixed(1);
    return '<span class="sn-react ' + (trend === 'up' || trend === 'down' ? trend : '') + '" title="반응일 종가 ÷ 전날 종가">' + (t === '0.0' ? '' : r >= 0 ? '+' : '−') + t + '%</span>';
  }
  function item(x){
    var link = /^https:\/\//.test(x.url || '') ? '<a class="sn-source" href="' + esc(x.url) + '" target="_blank" rel="noopener noreferrer">' + esc(x.source || '출처') + ' ↗</a>' : '';
    return '<li class="sn-item">'
      + '<a class="sn-stock" href="' + esc(x.href) + '"><img src="logos/' + x.ticker.toLowerCase() + '.png" alt="" loading="lazy"><span><strong>' + esc(x.ticker) + '</strong><small>' + esc(x.name) + '</small></span></a>'
      + '<div class="sn-body"><div class="sn-label"><span class="sn-dot ' + x.category + '" title="' + LABEL[x.category] + '"></span>' + esc(x.heading) + '</div>'
      + '<p class="sn-title">' + esc(x.title) + '</p>' + link + '</div>'
      + react(x.reaction, x.trend) + '</li>';
  }
  function render(){
    var html = '', last = null, open = false;
    N.items.slice(0, shown).forEach(function(x){
      if (x.date !== last){ if (open) html += '</ul>'; html += '<h3 class="sn-day">' + day(x.date) + '</h3><ul class="sn-list">'; last = x.date; open = true; }
      html += item(x);
    });
    if (open) html += '</ul>';
    root.innerHTML = html + (shown < N.items.length ? '<button type="button" class="sn-more">이전 소식 더 보기</button>' : '');
  }
  root.addEventListener('click', function(e){
    if (!e.target.closest('.sn-more')) return;
    shown += STEP; render();
  });
  render();
})();
