const stocks=window.StockData.stocks;
const days=window.StockData.days;
let day=0,index=0;
const savedReading=Reading.load('today');
const explicitCard=Boolean(location.hash);
let saveReading=()=>{};
function render(){
 const d=stocks.find(s=>s.ticker===days[day].tickers[index]);
 document.getElementById('dates').innerHTML=days.map((v,i)=>`<button data-day="${i}" aria-pressed="${i===day}">${v.label}<small>${v.tickers.length}</small></button>`).join('');
 document.getElementById('day-title').textContent=days[day].full;
 document.getElementById('summary-context').textContent=days[day].label+' · '+d.ticker;
 document.getElementById('summary-title').textContent=d.name+' · 종목 요약';
 document.getElementById('selected-analysis').href=d.href;
 renderRelatedNews(d);
 window.TodaySelection={day,index,tickers:days[day].tickers};
 window.dispatchEvent(new Event('today-selection'));
}
function writeLocation(){const hash='#'+day+'-'+days[day].tickers[index];if(location.hash!==hash)history.pushState(null,'',hash);saveReading();}
function readLocation(){
 const match=location.hash.match(/^#(\d+)-([A-Z]+)$/);
 const n=match?Number(match[1]):0;
 const i=match?days[n]?.tickers.indexOf(match[2]):0;
 day=i>=0?n:0;index=i>=0?i:0;render();
 if(i===undefined||i<0)history.replaceState(null,'','#0-'+days[0].tickers[0]);
}
window.selectTodayStock=ticker=>{const next=days[day].tickers.indexOf(ticker);if(next<0)return;index=next;render();writeLocation();};
document.getElementById('dates').onclick=e=>{const b=e.target.closest('[data-day]');if(b){day=Number(b.dataset.day);index=0;render();writeLocation();}};
window.addEventListener('popstate',()=>{readLocation();saveReading();});
window.addEventListener('hashchange',()=>{readLocation();saveReading();});
if(!explicitCard&&Number.isInteger(savedReading.day)&&days[savedReading.day]?.tickers.includes(savedReading.ticker))history.replaceState(null,'','#'+savedReading.day+'-'+savedReading.ticker);
readLocation();
saveReading=Reading.bind('today',()=>({day,ticker:days[day].tickers[index]}),!explicitCard?savedReading.y:undefined);
window.addEventListener('quotes-updated',render);

function renderRelatedNews(d){
 document.getElementById('news-google').href='https://news.google.com/search?q='+encodeURIComponent(d.ticker+' stock');
 document.getElementById('news-youtube').href='https://www.youtube.com/results?search_query='+encodeURIComponent(d.ticker+' stock news');
 document.getElementById('news-company').textContent=d.name+' 관련 소식';
 window.renderNews(d.ticker);
}

function refreshCalendar(){const now=new Date();document.getElementById('calendar-today').textContent=new Intl.DateTimeFormat('ko-KR',{dateStyle:'full'}).format(now);document.getElementById('calendar-today').dateTime=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');}
refreshCalendar();setInterval(refreshCalendar,60000);

