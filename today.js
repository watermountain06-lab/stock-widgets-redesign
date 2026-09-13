const stocks=window.StockData.stocks;
const days=window.StockData.days;
let day=0,index=0;
const savedReading=Reading.load("today");
const explicitCard=Boolean(location.hash);
let saveReading=()=>{};
const story=document.getElementById('story');
function moveDay(n){day=n;index=0;render();writeLocation();}
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
 story.innerHTML=`<div class="stock-heading"><img src="logos/${d.ticker.toLowerCase()}.png" alt=""><div><small>${d.ticker} · ${d.sector}</small><h2>${d.name}</h2></div><a class="analysis-link" href="${d.href}">분석 보기 ↗</a></div><div class="quote-origin">${window.StockData.quoteLabel(d)}</div><div class="quote"><span class="price">${d.price}</span><span class="change ${d.change>=0?'up':'down'}">${d.change>=0?'+':'−'}${Math.abs(d.change).toFixed(2)}%</span><span class="compact-cap">시가총액 ${d.marketCap}</span></div><p class="caption">${d.quoteAsOf ? "Twelve Data · 시세 기준 "+d.quoteAsOf : ""}</p>`;

 document.getElementById('drag-hint').textContent=index===0?'← 카드를 왼쪽으로 드래그해 다음 종목 보기':index===list.length-1?'카드를 오른쪽으로 드래그해 이전 종목 보기 →':'↔ 카드를 좌우로 드래그해 종목 넘기기';
 document.getElementById('summary-context').textContent=days[day].label+' · '+d.ticker;
 renderWorkspace(d);
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
 writeLocation();

 const stage=document.querySelector('.stage');stage.append(outgoing);
 const timing={duration:300,easing:'linear',fill:'both'};
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

function writeLocation(){const hash='#'+day+'-'+days[day].tickers[index];if(location.hash!==hash)history.pushState(null,'',hash);saveReading();}
function readLocation(){
 const match=location.hash.match(/^#(\d+)-([A-Z]+)$/);
 const n=match?Number(match[1]):0;const i=match?days[n]?.tickers.indexOf(match[2]):0;
 day=i>=0?n:0;index=i>=0?i:0;render();
 if(i===undefined || i<0)history.replaceState(null,'','#0-'+days[0].tickers[0]);
}
window.addEventListener('popstate',()=>{readLocation();saveReading();});window.addEventListener('hashchange',()=>{readLocation();saveReading();});
if(!explicitCard && Number.isInteger(savedReading.day) && days[savedReading.day]?.tickers.includes(savedReading.ticker)){
 history.replaceState(null,'','#'+savedReading.day+'-'+savedReading.ticker);
}
readLocation();
saveReading=Reading.bind('today',()=>({day,ticker:days[day].tickers[index]}),!explicitCard?savedReading.y:undefined);
bindCardNavigation(document.querySelector('.stage'),moveCard);

window.addEventListener('quotes-updated',render);

function renderWorkspace(d){
 const key='today-work-'+days[day].label+'-'+d.ticker;
 let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')||{};if(typeof saved!=='object')saved={};}catch{}
 const tasks=document.getElementById('today-tasks');
 tasks.innerHTML=['실적과 공시 확인','가격 변동 배경 확인','토론할 질문 정리'].map((label,i)=>'<label><input type="checkbox" data-task="'+i+'">'+label+'</label>').join('');
 tasks.querySelectorAll('input').forEach((input,i)=>{input.checked=Boolean(saved[i]);input.addEventListener('change',()=>{saved[i]=input.checked;persist();});});
 const note=document.getElementById('discussion-note');note.value=typeof saved.note==='string'?saved.note:'';
 note.oninput=()=>{saved.note=note.value;persist();};
 document.getElementById('work-status').textContent='이 기기에 저장 · '+d.ticker;
 function persist(){try{localStorage.setItem(key,JSON.stringify(saved));document.getElementById('work-status').textContent='저장됨 · '+d.ticker;}catch{document.getElementById('work-status').textContent='저장할 수 없습니다. 브라우저 저장 설정을 확인하세요.';}}
 document.getElementById('news-google').href='https://news.google.com/search?q='+encodeURIComponent(d.ticker+' stock');
 document.getElementById('news-youtube').href='https://www.youtube.com/results?search_query='+encodeURIComponent(d.ticker+' stock news');
 document.getElementById('news-company').textContent=d.name+' 관련 소식';
 window.renderNews(d.ticker);
}

function refreshCalendar(){const now=new Date();document.getElementById('calendar-today').textContent=new Intl.DateTimeFormat('ko-KR',{dateStyle:'full'}).format(now);document.getElementById('calendar-today').dateTime=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');}
refreshCalendar();setInterval(refreshCalendar,60000);
