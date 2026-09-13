document.addEventListener('DOMContentLoaded',async()=>{
  const box=document.createElement('aside');box.className='data-status';
  box.textContent='데이터 출처: 프로젝트 예시 자료 · 시세 기준일: 미확인 · 마지막 시세 갱신: 없음 · 실시간/지연 시세 연결 전';
  const header=document.querySelector('.site-header');header.after(box);
  try {
    const response=await fetch('quotes-snapshot.json',{cache:'no-store'});
    if(!response.ok)return;
    const data=await response.json();
    if(data.source!=='Twelve Data'||!Array.isArray(data.quotes)||!Number.isFinite(Date.parse(data.updatedAt)))return;
    let count=0;
    for(const quote of data.quotes){
      const stock=window.StockData.stocks.find(s=>s.ticker===quote.ticker);
      if(!stock||quote.currency!=='USD'||!Number.isFinite(quote.price)||quote.price<=0||!Number.isFinite(quote.change)||!Number.isFinite(Date.parse(quote.asOf)))continue;
      stock.price='$'+quote.price.toFixed(2);stock.change=quote.change;stock.quoteAsOf=quote.asOf;count++;
    }
    if(count){
      const dates=data.quotes.map(q=>q.asOf).filter(d=>Number.isFinite(Date.parse(d))).sort();
      box.textContent='저장 시세: Twelve Data · '+count+'개 종목 · 시세 기준 '+dates[0]+' ~ '+dates.at(-1)+' · 파일 갱신 '+data.updatedAt+' · 지연 시간 미확인 · 나머지 종목·시가총액·시장 지표는 예시 데이터';
      window.dispatchEvent(new Event('quotes-updated'));
    }
  } catch { /* Keep the clearly labelled demo if a snapshot is unavailable. */ }
});
