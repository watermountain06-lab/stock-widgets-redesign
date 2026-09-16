document.addEventListener('DOMContentLoaded',async()=>{
  const box=document.createElement('aside');box.className='data-status';
  const meta=window.StockData.meta;
  box.textContent='데이터 출처: '+meta.source+' · 시세 기준일: '+meta.asOf+' · 재무점수 평가 기준 '+meta.scoreValuationAsOfMin+' ~ '+meta.scoreValuationAsOfMax+' · 실시간 아님 · 시장 지표와 Today 날짜 편성은 예시';
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
      if(stock.quoteDate && Date.parse(quote.asOf)<Date.parse(stock.quoteDate+'T23:59:59Z'))continue;
      stock.quoteDate=quote.asOf;stock.quoteSource='Twelve Data';stock.priceStale=false;
      stock.price='$'+quote.price.toFixed(2);stock.change=quote.change;stock.quoteAsOf=quote.asOf;count++;
    }
    if(count){
      const dates=data.quotes.map(q=>q.asOf).filter(d=>Number.isFinite(Date.parse(d))).sort();
      box.textContent='저장 시세: Twelve Data · '+count+'개 종목 · 시세 기준 '+dates[0]+' ~ '+dates.at(-1)+' · 파일 갱신 '+data.updatedAt+' · 지연 시간 미확인 · 나머지 종목·시가총액·평가는 main 저장 데이터 · 시장 지표는 예시';
      window.dispatchEvent(new Event('quotes-updated'));
    }
  } catch { /* Keep the clearly labelled demo if a snapshot is unavailable. */ }
});
