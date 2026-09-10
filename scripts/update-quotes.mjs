// Run locally or in a trusted job. Never put the API key in browser files.
import fs from 'node:fs';
import vm from 'node:vm';
const apiKey=process.env.TWELVE_DATA_API_KEY;
if(!apiKey)throw new Error('TWELVE_DATA_API_KEY is required. No quote file was changed.');
const scope={window:{}};vm.runInNewContext(fs.readFileSync(new URL('../stock-data.js',import.meta.url),'utf8'),scope);
const quotes=[];
for(const stock of scope.window.StockData.stocks){
  if(stock.ticker==='SPCX')continue; // Symbol/listing has not been verified.
  const symbol=stock.ticker==='BRKB'?'BRK.B':stock.ticker;
  const response=await fetch('https://api.twelvedata.com/quote?symbol='+encodeURIComponent(symbol),{headers:{Authorization:'apikey '+apiKey},signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw new Error('Quote request failed: '+response.status);
  const q=await response.json();
  if(q.status==='error'||!q.close||!q.timestamp||!Number.isFinite(Number(q.percent_change)))throw new Error('Invalid quote for '+symbol+'. Existing snapshot preserved.');
  quotes.push({ticker:stock.ticker,price:Number(q.close),change:Number(q.percent_change),asOf:new Date(q.timestamp*1000).toISOString(),currency:q.currency});
  await new Promise(resolve=>setTimeout(resolve,8500));
}
const snapshot={source:'Twelve Data',sourceUrl:'https://twelvedata.com',updatedAt:new Date().toISOString(),delayMinutes:null,quotes};
fs.writeFileSync(new URL('../quotes-snapshot.json',import.meta.url),JSON.stringify(snapshot,null,2)+'\n');
console.log('Saved '+quotes.length+' quotes. Confirm your plan’s display rights before publishing.');
