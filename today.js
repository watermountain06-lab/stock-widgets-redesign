const stocks = [
    {rank:1, ticker:'NVDA', name:'엔비디아', sector:'반도체',            price:'$228.45', change:1.80,  marketCap:'$5.55T', href:'cards/NVDA_full_widget.html'},
    {rank:2, ticker:'AAPL', name:'애플',      sector:'하드웨어',          price:'$325.13', change:2.61,  marketCap:'$4.76T', href:'cards/AAPL_full_widget.html'},
    {rank:3, ticker:'GOOGL',name:'알파벳',    sector:'인터넷&middot;플랫폼',   price:'$335.02', change:-1.28, marketCap:'$4.10T', href:'cards/GOOGL_full_widget.html'},
    {rank:4, ticker:'MSFT', name:'마이크로소프트', sector:'소프트웨어',   price:'$501.02', change:-1.24, marketCap:'$3.72T', href:'cards/MSFT_full_widget.html'},
    {rank:5, ticker:'AMZN', name:'아마존',    sector:'이커머스&middot;클라우드', price:'$256.36', change:-1.51, marketCap:'$2.76T', href:'cards/AMZN_full_widget.html'},
    {rank:6, ticker:'TSM',  name:'TSMC',     sector:'반도체&middot;파운드리',  price:'$424.15', change:1.55,  marketCap:'$2.20T', href:'cards/TSM_full_widget.html'},
    {rank:7, ticker:'SPCX', name:'스페이스X', sector:'우주항공&middot;위성통신&middot;AI', price:'$147.76', change:5.01, marketCap:'$1.95T', href:'cards/SPCX_full_widget.html'},
    {rank:8, ticker:'AVGO', name:'브로드컴',   sector:'반도체&middot;인프라SW', price:'$367.24', change:-0.66, marketCap:'$1.79T', href:'cards/AVGO_full_widget.html'},
    {rank:9, ticker:'META', name:'메타 플랫폼스', sector:'SNS 광고&middot;AI', price:'$571.10', change:-0.90, marketCap:'$1.47T', href:'cards/META_full_widget.html'},
    {rank:10, ticker:'TSLA', name:'테슬라',    sector:'EV&middot;자율주행',    price:'$367.95', change:5.51,  marketCap:'$1.45T', href:'cards/TSLA_full_widget.html'},
    {rank:11, ticker:'BRKB', name:'버크셔 해서웨이', sector:'금융&middot;복합기업', price:'$508.13', change:0.57, marketCap:'$1.09T', href:'cards/BRKB_full_widget.html'},
    {rank:12, ticker:'MU', name:'마이크론 테크놀로지', sector:'반도체&middot;메모리', price:'$958.16', change:0.22, marketCap:'$1.08T', href:'cards/MU_full_widget.html'}
  ];
const days=[{label:'9월 10일 (목)',full:'2026년 9월 10일 (목)',tickers:['NVDA','AAPL','GOOGL','MSFT','AMZN','TSM']},{label:'9월 9일 (수)',full:'2026년 9월 9일 (수)',tickers:['TSLA','SPCX','AVGO','META']},{label:'9월 8일 (화)',full:'2026년 9월 8일 (화)',tickers:['BRKB','MU']}];
let day=0,index=0;
const story=document.getElementById('story');
function moveDay(n){day=n;index=0;render();}
function preview(d){return '<span>'+d.sector+'</span><strong>'+d.name+'</strong><span>'+d.ticker+'</span><strong>'+d.price+'</strong><span class="preview-lines" aria-hidden="true"></span>';}
let cardAnimations=[];
function clearCardAnimations(){
 cardAnimations.forEach(a=>a.cancel());cardAnimations=[];
 document.querySelectorAll('.departing-card').forEach(el=>el.remove());
}
function render(){
 clearCardAnimations();
 const list=days[day].tickers.map(t=>stocks.find(s=>s.ticker===t));const d=list[index];
 document.getElementById('dates').innerHTML=days.map((v,i)=>`<button data-day="${i}" aria-pressed="${i===day}">${v.label}<small>${v.tickers.length}</small></button>`).join('');
 document.getElementById('day-title').textContent=days[day].full;

 ['preview-next'].forEach(id=>document.getElementById(id).disabled=index===list.length-1);
 const prev=document.getElementById('preview-previous');prev.hidden=index===0;
 prev.innerHTML=index>0?preview(list[index-1]):'';
 const next=document.getElementById('preview-next');next.hidden=index===list.length-1;
 if(index<list.length-1)next.innerHTML=preview(list[index+1]);
 story.innerHTML=`<span class="bookmark">${d.sector}</span><div class="stock-heading"><img src="logos/${d.ticker.toLowerCase()}.png" alt=""><div><small>TODAY'S COMPANY · ${d.ticker}</small><h2>${d.name}</h2></div></div><p class="intro">${d.name}의 숫자와 사업을 한 장에.<br>가격부터 업종, 상세 분석까지 차례로 살펴보세요.</p><div class="quote"><span class="price">${d.price}</span><span class="change ${d.change>=0?'up':'down'}">${d.change>=0?'+':'−'}${Math.abs(d.change).toFixed(2)}%</span></div><p class="caption">가격·등락률은 레이아웃 시연용 예시 값입니다.</p><div class="metrics"><div class="metric"><span>시가총액</span><strong>${d.marketCap}</strong></div><div class="metric"><span>시가총액 순위</span><strong>${d.rank}위</strong></div><div class="metric"><span>티커</span><strong>${d.ticker}</strong></div></div><section class="section"><h3><span>01</span>기업 살펴보기</h3><p>이 종목은 ${d.sector} 업종으로 분류되어 있습니다. 사업 구조와 실적, 주요 이벤트는 종합 분석 페이지에서 확인할 수 있습니다.</p></section><section class="section"><h3><span>02</span>함께 살펴볼 종목</h3><p>오늘의 목록에서 다른 기업의 숫자도 비교해 보세요.</p><div class="comparison">${list.filter(s=>s.ticker!==d.ticker).slice(0,2).map(s=>`<a href="${s.href}"><small>${s.name}</small><strong>${s.ticker} ↗</strong><b>${s.price}</b></a>`).join('')}</div></section><section class="section"><h3><span>03</span>분석 이어 읽기</h3><a class="source-link" href="${d.href}">기업 개요 · 재무 · 기술적 분석<span>종합 분석 ↗</span></a><a class="source-link" href="index.html">전체 기업을 한눈에<span>종목 목록 ↗</span></a></section><details><summary>ⓘ 이 카드의 데이터 범위</summary><p>날짜별 목록과 시세는 디자인 확인을 위한 예시입니다. 실제 해당 날짜의 가격이나 추천 종목을 의미하지 않습니다. 시가총액 순위는 프로젝트에 포함된 예시 종목 기준입니다. 최신 공시 및 시세 검증은 별도로 필요합니다.</p></details><a class="full-link" href="${d.href}">${d.ticker} 상세 분석 보기 ↗</a>`;
 document.getElementById('previous').disabled=index===0;document.getElementById('next').disabled=index===list.length-1;
 document.getElementById('dots').innerHTML=list.map((s,i)=>`<button class="dot" data-index="${i}" aria-label="${i+1}번째 종목 ${s.ticker}" aria-pressed="${i===index}"></button>`).join('');
 document.getElementById('position').textContent=`◆ ${String(index+1).padStart(2,'0')} / ${String(list.length).padStart(2,'0')} · ${d.ticker}`;
}
document.getElementById('dates').addEventListener('click',e=>{const b=e.target.closest('[data-day]');if(b)moveDay(Number(b.dataset.day));});
document.getElementById('dots').addEventListener('click',e=>{const b=e.target.closest('[data-index]');if(b)moveCard(Number(b.dataset.index)-index);});
function moveCard(step){
 const nextIndex=index+step;
 if(!step || nextIndex<0 || nextIndex>=days[day].tickers.length)return;
 clearCardAnimations();
 const direction=Math.sign(step);
 const outgoing=story.cloneNode(true);
 outgoing.removeAttribute('id');outgoing.classList.add('departing-card');
 outgoing.setAttribute('aria-hidden','true');outgoing.inert=true;
 outgoing.querySelectorAll('[id]').forEach(el=>el.removeAttribute('id'));
 const distance=story.getBoundingClientRect().width+28;
 index=nextIndex;render();
 history.pushState(null,'','#'+day+'-'+days[day].tickers[index]);

 const stage=document.querySelector('.stage');stage.append(outgoing);
 const timing={duration:500,easing:'linear',fill:'both'};
 const exit=outgoing.animate([
  {transform:'translateX(0) scale(1) rotateY(0deg)',opacity:1,filter:'blur(0px)'},
  {transform:'translateX('+(-direction*distance)+'px) scale(.88) rotateY('+(direction*12)+'deg)',opacity:0,filter:'blur(2px)'}
 ],timing);
 const enter=story.animate([
  {transform:'translateX('+(direction*distance)+'px) scale(.88) rotateY('+(-direction*12)+'deg)',opacity:.3,filter:'blur(2px)'},
  {transform:'translateX(0) scale(1) rotateY(0deg)',opacity:1,filter:'blur(0px)'}
 ],timing);
 cardAnimations=[exit,enter];
 Promise.all(cardAnimations.map(a=>a.finished)).then(()=>{outgoing.remove();exit.cancel();enter.cancel();}).catch(()=>{});
}

['previous','preview-previous'].forEach(id=>document.getElementById(id).addEventListener('click',()=>moveCard(-1)));
['next','preview-next'].forEach(id=>document.getElementById(id).addEventListener('click',()=>moveCard(1)));
render();

function readLocation(){const match=location.hash.match(/^#(\d+)-([A-Z]+)$/);if(match){const n=Number(match[1]);const i=days[n]?.tickers.indexOf(match[2]);if(i>=0){day=n;index=i;render();}}}
window.addEventListener('popstate',readLocation);readLocation();

