// ETF 홈 구역(2026-10-19, 2026-10-20 지수·ETF 탭; 2026-10-21부터 preview·라이브 공용 화면 코드 — pipeline/site_ui/UI_DIFF.md etf).
// 홈 "시장 지표" 구역 제목 줄에 [시장 지표] [지수·ETF] 탭을 넣고, 지수·ETF 탭에서는 시장 지표와 같은 회전 화면에 ETF마다 카드 하나를 보인다.
// 카드를 누르면 ETF 카드 페이지(시세·수익률·구성 종목·사건·카드 판정 탭)로 간다. 값은 홈 ETF 데이터 파일(window.ETF_DATA)에서 읽는다 —
// 캐시를 피해 5분 단위 시각을 붙여 직접 불러온다(loadData). 파일 이름은 pageHref·dataSrc 두 곳 — 기본값은 라이브 이름(etf-<티커>.html,
// etf-data.js)이고, 이름이 다른 사이트는 이 파일보다 먼저 window.ETF_FILES = {page: 접두, data: 파일}을 둔다.
// 규칙(v2/research/etf_verdict_prereg.md): 참고용·매수 기준 아님. builtFor가 홈 세션(StockData.meta.priceSession)과 다르면
// 묵음 — 판정·점수를 지우고 사유만 보인다. 데이터 파일이 없거나 깨져 ETF_DATA가 없으면 "불러오지 못함"을 보인다.
(function () {
  // 카드 순서. 새 ETF는 etf_daily.py·사전 등록, 카드 생성기(v2/index/index_daily.py PROFILES)에 더한 뒤 여기에.
  var ORDER = ['SPY', 'QQQ', 'DIA', 'IWM', 'TLT', 'GLD'];
  // 가격형(판정 없음) — 값 = 허용 대조 방식(check). 카드 생성기(PROFILES homePrice)만 더하면 된다. 자료가 없어도 가격형으로 그린다.
  var PRICE_ONLY = {IWM: 'day', TLT: 'day', GLD: 'history'};
  // 카드 머리: 티커를 크게, 옆에 무엇을 따라가는지(2026-10-21 — 11px 회색 한 줄이라 티커가 잘 안 보였다)
  var NAMES = {SPY: 'S&P 500', QQQ: '나스닥 100', DIA: '다우존스 30', IWM: '러셀 2000', TLT: '미국 국채 20년+', GLD: '금'};
  var TIERS = ['저평가', '적정~저평가', '적정', '적정~고평가', '고평가', '카드 없음', '판정 보류', '그 밖 제외', '분류 안 됨'];

  function pct(x, d) { return x == null ? '—' : (x * 100).toFixed(d == null ? 1 : d) + '%'; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  function fin(x) { return typeof x === 'number' && isFinite(x); }
  // 형식 검사 — 어긋나면 "형식 오류" 보류로 그린다(값을 짐작해 채우지 않는다).
  function valid(d) {
    if (!d || typeof d !== 'object' || (d.status !== 'ok' && d.status !== 'held')) return false;
    if (d.status === 'held') return typeof d.reasonText === 'string';
    // 정상 판정은 규칙(v2/research/etf_verdict_prereg.md)이 낼 수 있는 값만 받는다: 점수 [−4, +3], 덮은 비중 [0.70, 1],
    // 막대 9칸이 모두 0~1이고 합 1, 5등급 합 = 덮은 비중, 상위 비중 0~1.
    if (TIERS.slice(0, 5).indexOf(d.verdict) < 0 || !fin(d.nbar) || d.nbar < -4 || d.nbar > 3) return false;
    if (!fin(d.coverage) || d.coverage < 0.7 || d.coverage > 1) return false;
    if (!d.bar || typeof d.bar !== 'object' || Array.isArray(d.bar)) return false;
    if (!TIERS.every(function (k) { return fin(d.bar[k]) && d.bar[k] >= 0 && d.bar[k] <= 1; })) return false;
    var sum = TIERS.reduce(function (a, k) { return a + d.bar[k]; }, 0);
    var five = TIERS.slice(0, 5).reduce(function (a, k) { return a + d.bar[k]; }, 0);
    if (Math.abs(sum - 1) > 1e-6 || Math.abs(five - d.coverage) > 1e-6) return false;
    if (!Array.isArray(d.top) || !d.top.every(function (t) { return t && typeof t.company === 'string' && fin(t.weight) && t.weight >= 0 && t.weight <= 1; })) return false;
    if (d.expense != null && (typeof d.expense !== 'object' || !fin(d.expense.pct))) return false;
    if (d.pending != null && (typeof d.pending !== 'object' || ['issuer_lag', 'home_lag'].indexOf(d.pending.kind) < 0
        || typeof d.pending.P !== 'string')) return false;
    return typeof d.S === 'string';
  }

  // 카드 하나 — 시장 지표 카드(flow.css .macro-flow-card)와 같은 모양.
  var FILES = window.ETF_FILES || {};
  function pageHref(t) { return (FILES.page || 'etf-') + t.toLowerCase() + '.html'; }
  function dataSrc() { return FILES.data || 'etf-data.js'; }

  function head(t, kind) {
    return '<span class="etf-tk">' + esc(t) + '</span><span class="etf-nm">' + esc(NAMES[t] || '') + '</span>'
      + '<span class="etf-kind">' + kind + '</span>';
  }
  function card(href, label, body) {
    return '<a class="macro-flow-card etf-card" href="' + href + '">'
      + '<div class="etf-card-label">' + label + '</div>' + body + '</a>';
  }

  // 가격형 칸(kind price, 판정 없음 — IWM·TLT·GLD, 2026-10-21): 정상은 종가·하루 등락·1년 수익률·대조 정보, 보류는 사유만.
  // check: day(최근 하루 NAV — navDate ∈ {builtFor, prevSession}) / history(GLD — 운용사 종가와 since~checkedThrough 날마다).
  // check가 없는 칸은 IWM만 예전 형식으로 받는다(새 JS가 먼저 배포되고 카드 단계가 아직 돌지 않은 사이 — 설계 dr r3).
  function isDay(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    var t = new Date(s + 'T00:00:00Z');   // 날짜만 — UTC로 읽고 UTC로 되돌린다(로컬 시간대 끼우지 않음)
    return !isNaN(t.getTime()) && t.toISOString().slice(0, 10) === s;
  }
  function validPrice(t, d) {
    if (!d || d.kind !== 'price' || d.etf !== t || (d.status !== 'ok' && d.status !== 'held') || typeof d.builtFor !== 'string') return false;
    if (d.status === 'held') return typeof d.reasonText === 'string';
    if (!(fin(d.close) && d.close > 0 && fin(d.chg) && fin(d.ret1y) && typeof d.S === 'string')) return false;
    if (d.check == null) return t === 'IWM' && typeof d.navDate === 'string';   // 예전 IWM 칸
    if (d.check !== PRICE_ONLY[t] || d.S !== d.builtFor || !isDay(d.builtFor) || !isDay(d.prevSession) || !(d.prevSession < d.builtFor)) return false;
    if (d.check === 'day') return isDay(d.navDate) && (d.navDate === d.builtFor || d.navDate === d.prevSession);
    if (!isDay(d.since) || !isDay(d.checkedThrough) || !(d.since <= d.checkedThrough)) return false;
    return (d.checkedThrough === d.builtFor && d.pendingDate === null)
      || (d.checkedThrough === d.prevSession && d.pendingDate === d.builtFor);
  }

  function priceCard(t, d) {
    var session = ((window.StockData || {}).meta || {}).priceSession;
    var href = pageHref(t);
    var label = head(t, 'ETF · 가격 카드');
    function held(why) {
      return card(href, label, '<div class="etf-card-main etf-held">시세 보류</div><div class="etf-card-sub etf-held">' + why + '</div>'
        + '<div class="etf-card-go">ETF 카드 ↗</div>');
    }
    if (!validPrice(t, d)) return held(d ? 'ETF 자료 형식 오류' : 'ETF 자료를 불러오지 못함');
    if (d.builtFor !== session) return held('갱신 대기(ETF ' + esc(d.builtFor) + ' · 홈 ' + esc(session || '—') + ')');
    if (d.status !== 'ok') return held(esc(d.reasonText));
    var up = function (x) { return '<span style="color:' + (x >= 0 ? 'var(--up)' : 'var(--down)') + '">' + (x >= 0 ? '+' : '−') + Math.abs(x * 100).toFixed(2) + '%</span>'; };
    var dot = function (s) { return esc(s.slice(5).replace(/-/g, '.')); };   // 월.일만 — 카드 한 줄에 맞춘다
    var tag;   // 한 줄(2026-10-21 — 두 줄씩 접혀 카드가 칸보다 컸다). 자세한 설명은 ETF 카드 페이지에 있다.
    if (d.check === 'history') {
      tag = '운용사 종가와 ' + esc(d.since.slice(0, 4)) + '년부터 매일 대조' + (d.pendingDate ? ' · ' + dot(d.pendingDate) + ' 대조 전' : '');   // 대조 시작은 자료에서
    } else {
      tag = (t === 'TLT' ? '분배금 제외 · ' : '') + 'NAV 하루만 대조(' + dot(d.navDate) + ')';
    }
    return card(href, label,
      '<div class="etf-card-main etf-tab">' + d.close.toFixed(2) + '</div>'
      + '<div class="etf-card-sub">하루 ' + up(d.chg) + ' · 1년 ' + up(d.ret1y) + '</div>'
      + '<div class="etf-card-tag">' + tag + '</div>'
      + '<div class="etf-card-go">ETF 카드 ↗</div>');
  }

  function etfCard(t, d) {
    if (PRICE_ONLY[t]) return priceCard(t, d);
    var session = ((window.StockData || {}).meta || {}).priceSession;
    var href = pageHref(t);
    function held(why) {
      return card(href, head(t, 'ETF'), '<div class="etf-card-main etf-held">판정 보류</div>'
        + '<div class="etf-card-sub etf-held">' + why + '</div><div class="etf-card-go">ETF 카드 ↗</div>');
    }
    if (!d) return held('ETF 자료를 불러오지 못함');
    if (!valid(d)) return held('ETF 자료 형식 오류');
    // 갱신 대기(2026-10-20): ETF 단계가 "날짜만 어긋나 직전 판정을 유지했다"고 적은 경우만 묵음 대신 판정을 보인다.
    // 브라우저는 달력을 다시 계산하지 않고 ETF 단계가 쓴 pending.P만 홈 세션과 비교한다.
    var pd = d.status === 'ok' && d.pending ? d.pending : null;
    var lagIssuer = !!(pd && pd.kind === 'issuer_lag' && pd.P === session);
    var lagHome = !!(pd && pd.kind === 'home_lag' && d.builtFor === session);
    var stale = !d.builtFor || (d.builtFor !== session && !lagIssuer);
    if (stale) return held('묵음(ETF ' + esc(d.builtFor || '—') + ' · 홈 ' + esc(session || '—') + ')');
    if (d.status !== 'ok') return held(esc(d.reasonText));
    var bar = TIERS.map(function (k, i) {
      var w = (d.bar || {})[k];
      return w ? '<span class="etf-seg etf-seg-' + i + '" style="width:' + (w * 100).toFixed(3) + '%" title="' + esc(k) + ' ' + pct(w) + '"></span>' : '';
    }).join('');
    var tag = lagIssuer ? '운용사 파일 갱신 대기 · 판정 기준 ' + esc(d.builtFor) : lagHome ? '홈 가격 세션 갱신 대기' : d.edgeNear ? '경계 근처' : '';
    return card(href, head(t, 'ETF'),
      '<div class="etf-card-main">' + esc(d.verdict) + '</div>'
      + '<div class="etf-card-tag">카드가 덮은 비중 <span class="etf-tab">' + pct(d.coverage) + '</span></div>'
      + '<div class="etf-bar" role="img" aria-label="등급별 보유 비중">' + bar + '</div>'
      + (tag ? '<div class="etf-card-tag">' + tag + '</div>' : '')
      + '<div class="etf-card-go">ETF 카드 ↗</div><div class="etf-ref">참고용 · 매수 기준 아님</div>');
  }

  function cardsHtml() {
    var all = window.ETF_DATA || {}, out = [];   // S&P 500 지수 카드는 빼고 ETF만(2026-10-20 사용자 결정 — 지수 카드 틀은 SPY 카드가 됐다)
    ORDER.forEach(function (t) {
      try { out.push(etfCard(t, all[t])); }
      catch (e) { out.push(card(pageHref(t), head(t, 'ETF'), '<div class="etf-card-main etf-held">판정 보류</div><div class="etf-card-sub etf-held">ETF 자료 형식 오류</div>')); }
    });
    return out;
  }

  // 회전 화면 — flow.js의 flowing()과 같은 움직임(그 함수는 밖으로 나오지 않아 preview 쪽에 줄여 옮겼다; 클래스·CSS는 flow.css 그대로).
  // 카드가 적으면 한 장이 가까운 거리에서 반대편으로 건너뛰어 보이므로, 7장이 넘을 때까지 같은 목록을 되풀이해 건너뛰기가
  // 보이지 않는 거리(3칸 넘어 — 그려지지 않음)에서 일어나게 한다. 번호(01 / 02)는 실제 카드 수로 센다.
  function flow(container, htmls) {
    var n = htmls.length, reps = n === 1 ? 1 : Math.ceil(7 / n), total = n * reps;   // 한 장이면 돌리지 않는다. 7장 이상이어야 건너뛰기가 숨는 거리(3칸 넘어)에서 일어난다
    var viewport = document.createElement('div');
    viewport.className = 'coverflow continuous-flow';
    viewport.tabIndex = 0;
    viewport.setAttribute('aria-label', '카드 탐색 · 좌우 방향키로 이동');
    var status = document.createElement('p');
    status.className = 'coverflow-status';
    var tmp = document.createElement('div');
    tmp.innerHTML = Array(reps + 1).join(htmls.join(''));
    var cards = Array.prototype.slice.call(tmp.children);
    var index = 0, position = 0, manual = null, prev = null, frame;
    var reduced = matchMedia('(prefers-reduced-motion: reduce)');
    cards.forEach(function (c, i) {
      c.classList.add('coverflow-card');
      c.addEventListener('click', function (e) { if (i !== index) { e.preventDefault(); focusCard(i); } });   // 가운데 카드만 링크로
      viewport.appendChild(c);
    });
    function render() {
      cards.forEach(function (c, i) {
        var off = ((i - position) % total + total) % total;
        if (off > total / 2) off -= total;
        var dist = Math.abs(off);
        c.style.setProperty('--offset', off);
        c.style.setProperty('--distance', dist);
        c.style.zIndex = String(100 - Math.round(dist * 10));
        c.classList.toggle('is-current', i === index);
        c.style.visibility = dist > 3 ? 'hidden' : 'visible';
        c.setAttribute('aria-hidden', String(dist > 3));
        c.tabIndex = dist > 3 ? -1 : 0;
      });
      status.textContent = String(index % n + 1).padStart(2, '0') + ' / ' + String(n).padStart(2, '0');
    }
    function tick(now) {
      if (!viewport.isConnected) return;
      var dt = prev === null ? 0 : Math.min(now - prev, 50);
      prev = now;
      // 탭이 숨었거나 구역이 접혔으면 쉰다. 한 장이면 처음 한 번만 그리고 멈춘다.
      if (total === 1) return;
      if (!document.hidden && !viewport.closest('[hidden]') && !viewport.closest('details:not([open])')) {
        if (manual) {
          var t = Math.min(1, (now - manual.start) / 1200), e = t * t * (3 - 2 * t);
          position = manual.from + (manual.to - manual.from) * e;
          if (t === 1) manual = null;
        } else if (!reduced.matches && total > 1) position += dt / 6500;
        position = (position + total) % total;
        index = Math.round(position) % total;
        render();
      }
      frame = requestAnimationFrame(tick);
    }
    function focusCard(d) {
      while (d - position > total / 2) d -= total;
      while (d - position < -total / 2) d += total;
      if (reduced.matches) { position = (d + total) % total; index = Math.round(position) % total; render(); }
      else manual = {from: position, to: d, start: performance.now()};
    }
    viewport.onkeydown = function (e) {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); focusCard(index + (e.key === 'ArrowLeft' ? -1 : 1)); }
    };
    var tx = null;
    viewport.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; }, {passive: true});
    viewport.addEventListener('touchend', function (e) {
      if (tx !== null) { var dx = e.changedTouches[0].clientX - tx; if (Math.abs(dx) > 45) focusCard(index + (dx < 0 ? 1 : -1)); tx = null; }
    }, {passive: true});
    container.replaceChildren(viewport, status);
    render();
    frame = requestAnimationFrame(tick);
  }

  // 시장 지표 구역 제목 줄에 [시장 지표] [지수·ETF] 탭(2026-10-20 사용자 요청) — 누른 쪽의 카드가 같은 자리 회전 화면에 나온다.
  // 구역 전체 접기(▾)는 그대로 두고, 탭을 누를 때는 접히지 않게 한다.
  function init() {
    var market = document.querySelector('details.market-demo');
    if (!market || market.querySelector('.etf-tabs')) return;
    var summary = market.querySelector('summary');
    var macroPane = summary.nextElementSibling;
    while (macroPane && macroPane.nodeType === 1 && macroPane.tagName === 'SCRIPT') macroPane = macroPane.nextElementSibling;
    var tabs = document.createElement('span');
    tabs.className = 'etf-tabs';
    tabs.setAttribute('role', 'tablist');
    tabs.innerHTML = '<button type="button" role="tab" data-pane="macro" aria-selected="true">시장 지표</button>'
      + '<button type="button" role="tab" data-pane="etf" aria-selected="false">지수·ETF</button>';
    Array.prototype.slice.call(summary.childNodes).forEach(function (x) {   // 제목 글자 "시장 지표"를 탭으로 바꾼다
      if (x.nodeType === 3 && x.textContent.trim()) x.textContent = '';
    });
    summary.insertBefore(tabs, summary.firstChild);
    var pane = document.createElement('div');
    pane.className = 'etf-pane';
    pane.hidden = true;
    pane.innerHTML = '<div class="wrap"><div class="market-flow etf-flow"></div></div>';
    macroPane.parentNode.insertBefore(pane, macroPane.nextSibling);
    var box = pane.querySelector('.etf-flow');
    function build() { flow(box, cardsHtml()); }
    tabs.addEventListener('click', function (e) {
      var b = e.target.closest('[data-pane]');
      if (!b) return;
      e.preventDefault();   // summary 안 — 구역이 접히지 않게
      if (!market.open) market.open = true;
      var etf = b.dataset.pane === 'etf';
      macroPane.hidden = etf;
      pane.hidden = !etf;
      tabs.querySelectorAll('[data-pane]').forEach(function (x) { x.setAttribute('aria-selected', String(x === b)); });
    });
    box.innerHTML = '<p class="coverflow-status">불러오는 중</p>';
    loadData(build);
    window.addEventListener('quotes-updated', function () { if (window.ETF_DATA !== undefined) build(); });
  }

  // 홈 데이터 파일은 매 실행 바뀌는데 주소가 같아 브라우저·Pages 캐시(최대 10분)에 옛 파일이 남는다 — 새 ETF가
  // "불러오지 못함"으로 보였다(2026-10-21). 5분 단위 시각을 붙여 직접 불러온다(index.html의 정적 줄은 뺐다). 실패하면 그대로 그린다.
  function loadData(done) {
    var s = document.createElement('script');
    s.src = dataSrc() + '?t=' + Math.floor(Date.now() / 300000);
    s.onload = s.onerror = function () { done(); };
    document.head.appendChild(s);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
