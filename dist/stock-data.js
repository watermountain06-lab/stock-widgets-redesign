// Single source for the demonstration catalog. No verified live quotes yet.
window.StockData={stocks:[
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
  ],days:[{label:'9월 10일 (목)',full:'2026년 9월 10일 (목)',tickers:['NVDA','AAPL','GOOGL','MSFT','AMZN','TSM']},{label:'9월 9일 (수)',full:'2026년 9월 9일 (수)',tickers:['TSLA','SPCX','AVGO','META']},{label:'9월 8일 (화)',full:'2026년 9월 8일 (화)',tickers:['BRKB','MU']}],meta:{mode:'demo',source:'프로젝트 예시 데이터',asOf:null,updatedAt:null,delayMinutes:null}};

// Explain the visible example selection without inventing valuation or news events.
window.StockData.selectionReason=function(d){
 if(d.ticker==='SPCX')return '예시 편성 · 상장 확인 전';
 const basis=d.quoteAsOf?'저장 시세 기준':'예시 시세 기준';
 if(d.change>=5)return '5% 이상 상승 · '+basis;
 if(d.change<=-5)return '5% 이상 하락 · '+basis;
 return '시가총액 '+d.rank+'위 · 등록 예시 종목 기준';
};

window.StockData.quoteLabel=function(d){return '';};
