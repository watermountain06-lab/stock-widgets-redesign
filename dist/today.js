// Tracking 탭 (2026-10-09, 이전 Today). 값은 tracking-data.js(scripts/build_tracking.py)에서 온다.
// 위: 날짜 버튼 · 그날의 저평가 목록(칩 + 흐르는 카드, flow.js) · 관찰 목록 토글.
// 가운데: 선택 종목 — 카드 밸류에이션 세 줄(자기 이력 대비 · 동종업 대비 · 현금흐름), 예상밴드 백테스트, 종합 해석 한 줄.
// 아래: 판정 성적표(판정일 종가 → 고른 날 종가 막대), 상세 표·변화 일지는 접어 둔다.
const stocks=window.StockData.stocks;
const T=window.TrackingData||{calls:[],journal:[],current:[],watch:[],detail:{},sessions:[],days:[],closes:{},judges:{}};
let day=T.days.length-1,index=0,whyOpen=false;
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const md=d=>d?Number(d.slice(5,7))+'/'+Number(d.slice(8,10)):'';
const money=v=>'$'+Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const pct=r=>r==null?'—':(r>0?'+':r<0?'−':'')+Math.abs(r*100).toFixed(1)+'%';
const cls=r=>r>0?'up':r<0?'down':'';
const name=t=>(stocks.find(s=>s.ticker===t)||{}).name||t;
const sign=v=>(v>0?'+':v<0?'−':'')+Math.abs(v);
const card=t=>'cards/'+encodeURIComponent(t)+'_full_widget.html';
// 홈 '평가 · 밴드 점수' 칸과 같은 표기
const bandText=b=>!b||b.pos==='none'?'밴드 없음':b.pos==='na'?'밴드 해당 없음':b.raw<-100?'밴드 표시 불가':'밴드 점수 '+String(b.score).replace('-','−');
const D=()=>T.days[day];
const tickers=()=>D()?D().list:[];
const session=()=>D()?D().session:T.asOf;
// 판정일부터 고른 날까지(그 전에 목록에서 나갔으면 나간 날까지)
function callOn(c,s){
 if(c.start>s)return null;
 const ended=c.end&&c.end<=s,at=ended?c.end:s,close=(T.closes[c.ticker]||{})[at];
 return close==null?null:{...c,at,close,ret:close/c.startClose-1,open:!ended,days:T.sessions.indexOf(at)-T.sessions.indexOf(c.start)};
}

function renderDays(){
 const d=D(),latest=day===T.days.length-1;
 document.getElementById('tk-title').textContent=latest?'지금 저평가 목록':md(d.session)+' 저평가 목록';
 document.getElementById('tk-meta').textContent=md(d.session)+' 종가 · '+d.list.length+'종목';
 document.getElementById('tk-days').innerHTML=T.days.map((x,i)=>`<button type="button" aria-pressed="${i===day}" data-day="${i}"><strong>${md(x.session)}</strong><span>${x.list.length}종목</span></button>`).join('');
 const rows=T.journal.filter(j=>j.session===d.session);
 document.getElementById('tk-change').textContent=day===0?'기록 시작일 · '+d.list.length+'종목이 이미 목록에 있었습니다'
  :rows.length?rows.map(j=>{const v=j.votes.length?' ('+j.votes.map(x=>`${x[0]} ${sign(x[1])} → ${sign(x[2])}`).join(', ')+')':'';
   return `${j.move==='in'?'▲':'▼'} ${j.ticker} ${j.list==='list'?'저평가 목록':'관찰 목록'}${j.move==='in'?'에 들어옴':'에서 나감'}${v}`;}).join(' · ')
  :'목록 변화 없음';
 document.getElementById('watch-count').textContent=d.watch.length+'종목';
 document.getElementById('tk-watch-list').innerHTML=d.watch.map(t=>`<a class="tk-chip" href="${card(t)}">${esc(t)} <small>${esc(name(t))}</small></a>`).join('')||'<span class="tk-note">없음</span>';
}

function renderChips(){
 document.getElementById('tk-chips').innerHTML=tickers().map((t,i)=>`<button type="button" class="tk-chip" aria-pressed="${i===index}" data-i="${i}">${esc(t)}</button>`).join('');
}

function renderStock(){
 const t=tickers()[index],panel=document.getElementById('tk-stock');
 panel.hidden=!t;if(!t)return;   // 목록이 빈 날에는 앞 날짜 종목을 남기지 않는다(Codex)
 const c=D().cards[t],j=T.judges[t]||{},x=T.detail[t]||{},s=x.summary;
 document.getElementById('tk-stock-title').innerHTML=`${esc(t)} <small>${esc(name(t))}</small>`;
 document.getElementById('tk-verdict').textContent=c.verdict;
 const pill=v=>`<span class="tk-pill ${/^싸다|^매우 싸다/.test(v||'')?'cheap':/비싸다/.test(v||'')?'dear':''}">${esc(v||'—')}</span>`;
 const meter=v=>{const n=Math.max(0,Math.min(100,Number(v)));return `<div class="tk-track tk-meter"><i style="left:30%"></i><i style="left:70%"></i><b style="left:${isFinite(n)?n:0}%"></b></div>`;};
 const basis='PER·PBR·PSR·PCR·EV/EBITDA';
 document.getElementById('tk-judges').innerHTML=
  `<div class="tk-judge"><div><strong>자기 이력 대비 <small>(지난 5년 ${basis})</small></strong>${pill(j.selfV)}</div><p>${esc(j.self||'—')}<small>/100</small></p>${meter(j.self)}</div>`
  +`<div class="tk-judge"><div><strong>동종업 대비 <small>(${esc(j.peerGroup?j.peerGroup+' 업종':'동종업')} ${basis})</small></strong>${pill(j.peerV)}</div><p>${esc(j.peer||'—')}<small>/100</small></p>${meter(j.peer)}</div>`
  +`<div class="tk-judge"><div><strong>현금흐름 (내재가치) <small>(DCF 기본 시나리오)</small></strong>${pill(j.dcfV)}</div><p>${esc(j.dcf||'—')} <small>현재가 대비 ${esc(j.up||'—')}</small></p><div class="tk-steps">${[0,1,2,3,4].map(i=>`<i class="${i===j.step?'on':''}"></i>`).join('')}</div></div>`;
 const b=c.band,pos=b&&b.score!=null&&b.raw>=-100?Math.max(0,Math.min(100,100-b.score)):null;
 document.getElementById('tk-band-track').innerHTML=pos==null?'':`<b style="left:${pos}%"></b>`;
 document.getElementById('tk-band-text').textContent=bandText(b);
 const clean=v=>String(v||'').replace(/^[^·]*·\s*/,'');   // "지배적 내러티브 · …", "🔍 다음 확인 포인트 · …"의 앞 꼬리표
 document.getElementById('summary-body').innerHTML=(s?`<p class="tk-head">${esc(clean(s.head))}</p>`+(s.next?`<p class="tk-next"><span>다음 확인</span> ${esc(clean(s.next))}</p>`:''):'<p>카드에 종합 해석이 없습니다.</p>')
  +`<div class="tk-actions">${s&&(s.points.length||s.counter)?`<button type="button" class="tk-btn" id="tk-why" aria-expanded="${whyOpen}">근거·반대 근거 ${whyOpen?'▴':'▾'}</button>`:''}<a class="tk-btn" href="${card(t)}">카드 열기 →</a><a class="tk-btn" href="market-news.html#stock-news-panel">${esc(t)} 소식 →</a></div>`
  +(s&&whyOpen?`<ul class="tk-why">${s.points.map(p=>`<li>${esc(p)}</li>`).join('')}${s.counter?`<li>${esc(clean(s.counter))}</li>`:''}</ul>`:'');
}

function renderBars(){
 const s=session(),rows=T.calls.map(c=>callOn(c,s)).filter(Boolean);
 document.getElementById('tracking-note').textContent=`기록 ${T.sessions.indexOf(s)+1}거래일(${md(T.firstSession)}~${md(s)}) · ${rows.length}건${rows.every(r=>r.open)?', 모두 진행 중':''}. 판정의 예측력은 확인되지 않았습니다.`;
 const max=Math.max(0.08,...rows.map(r=>Math.abs(r.ret)));
 document.getElementById('tk-bars').innerHTML=rows.map(r=>{
  const w=Math.abs(r.ret)/max*36,up=r.ret>=0;
  return `<div class="tk-bar-row"><a href="${card(r.ticker)}"><strong>${esc(r.ticker)}</strong></a>`
   +`<div class="tk-bar"><i class="zero"></i><i class="fill ${up?'up':'down'}${r.open?' open':''}" style="${up?'left':'right'}:50%;width:${w}%"></i>`
   +`<span class="p0" style="${up?'right:50%':'left:50%'}">판정 ${money(r.startClose)}</span>`
   +`<span class="p1 ${cls(r.ret)}" style="${up?'left':'right'}:${50+w}%">${money(r.close)}</span></div>`
   +`<b class="${cls(r.ret)}">${pct(r.ret)}</b><small>${md(r.start)} · ${r.days}일${r.open?'':' · 나감'}</small></div>`;
 }).join('')||'<p class="tk-note">이 날짜까지 기록된 판정이 없습니다.</p>';
}

function renderTable(){
 const result=c=>c.result==='open'?'<span class="tk-badge">진행 중</span>':c.result==='up'?'<span class="tk-badge up">오름</span>':'<span class="tk-badge down">내림</span>';
 document.getElementById('tracking-calls').innerHTML='<thead><tr><th>종목</th><th>판정</th><th>판정일 · 종가</th><th>나간 날 · 종가</th><th>목록에 있던 동안</th><th>판정일 → 오늘</th><th>결과</th></tr></thead><tbody>'
  +T.calls.map(c=>`<tr><td><a href="${card(c.ticker)}"><strong>${esc(c.ticker)}</strong><small>${esc(c.name)}</small></a></td>`
   +`<td>${esc(c.verdict)}</td><td>${md(c.start)} · ${money(c.startClose)}${c.fromStart?'<small title="v2 판정 기록이 시작된 날에 이미 목록에 있었다">기록 시작일</small>':''}</td>`
   +`<td>${c.end?md(c.end)+' · '+money(c.endClose)+'<small>'+esc(c.endVerdict||'')+'(으)로</small>':'<small>목록에 있음</small>'}</td>`
   +`<td class="num ${cls(c.onList)}">${pct(c.onList)}</td><td class="num ${cls(c.sinceStart)}">${pct(c.sinceStart)}</td><td>${result(c)}</td></tr>`).join('')
  +'</tbody>';
 // 변화 일지: 최근 10거래일, '더 보기'로 10거래일씩
 const days=[...new Set(T.journal.map(j=>j.session))];let shown=10;
 const list=document.getElementById('tracking-journal');
 function draw(){
  const keep=new Set(days.slice(0,shown));let html='',last=null;
  for(const j of T.journal.filter(j=>keep.has(j.session))){
   if(j.session!==last){html+=`<li class="tk-day">${md(j.session)} 종가 기준</li>`;last=j.session;}
   const votes=j.votes.map(v=>`${esc(v[0])} ${sign(v[1])} → ${sign(v[2])}`).join(' · ');
   html+=`<li class="tk-row ${j.move}"><span class="tk-arrow">${j.move==='in'?'▲':'▼'}</span><a href="${card(j.ticker)}"><strong>${esc(j.ticker)}</strong> ${esc(j.name)}</a>`
    +`<span>${esc(j.from||'—')} → ${esc(j.to||'—')} <em>${j.list==='list'?'저평가 목록':'관찰 목록'}${j.move==='in'?'에 들어옴':'에서 나감'}</em></span>${votes?`<small>${votes}</small>`:''}<small>종가 ${money(j.close)}</small></li>`;
  }
  list.innerHTML=(html||'<li class="tk-day">아직 목록을 드나든 기록이 없습니다.</li>')+(days.length>shown?'<li><button type="button" class="tk-more">이전 기록 더 보기</button></li>':'');
 }
 list.addEventListener('click',e=>{if(e.target.closest('.tk-more')){shown+=10;draw();}});
 draw();
}

// flow.js가 읽는 선택 상태: 카드는 고른 날의 종가·판정·밴드 점수와 판정 뒤 수익률을 보여 준다
function publish(){
 const s=session();
 window.TodaySelection={day,index,tickers:tickers(),session:s,cards:tickers().map(t=>{
  const c=D().cards[t],call=T.calls.map(k=>callOn(k,s)).find(k=>k&&k.ticker===t&&k.open);
  return {ticker:t,name:name(t),close:c.close,verdict:c.verdict,band:bandText(c.band),ret:call?call.ret:null};})};
 window.dispatchEvent(new Event('today-selection'));
}
function select(i,fromFlow){
 index=i;renderChips();renderStock();
 if(!fromFlow){publish();history.replaceState(null,'','#'+tickers()[i]);}
 else window.TodaySelection.index=i;
}
window.selectTodayStock=t=>{const i=tickers().indexOf(t);if(i>=0)select(i,false);};
// 흐르는 카드가 가운데로 오면 아래 칸도 그 종목으로(2026-10-09 사용자 결정: 원래대로 흐르게)
window.centerTodayStock=i=>{if(i!==index&&i<tickers().length)select(i,true);};

document.getElementById('tk-days').addEventListener('click',e=>{const b=e.target.closest('[data-day]');if(!b)return;day=Number(b.dataset.day);index=0;renderDays();renderChips();renderStock();renderBars();publish();});
document.getElementById('tk-chips').addEventListener('click',e=>{const b=e.target.closest('[data-i]');if(b)select(Number(b.dataset.i),false);});
document.getElementById('summary-body').addEventListener('click',e=>{if(e.target.closest('#tk-why')){whyOpen=!whyOpen;renderStock();}});
document.getElementById('tk-watch-toggle').addEventListener('click',e=>{const b=e.currentTarget,open=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',String(open));b.lastElementChild.textContent=open?'▴':'▾';document.getElementById('tk-watch-list').hidden=!open;});

if(!T.days.length){document.getElementById('tk-title').textContent='판정 기록이 없습니다';}
else{
 const fromHash=tickers().indexOf(decodeURIComponent(location.hash.slice(1)));if(fromHash>=0)index=fromHash;
 renderDays();renderChips();renderStock();renderBars();renderTable();publish();
}
