(() => {
  const topics=[['all','전체'],['rates','금리'],['fx','환율'],['economy','경제'],['jobs','실업률'],['companies','기업']];
  const queries={all:'stock market economy',rates:'Federal Reserve interest rates',fx:'US dollar exchange rates',economy:'US economy inflation',jobs:'US unemployment jobs report',companies:'company earnings stocks'};
  const list=document.getElementById('press-list'),status=document.getElementById('news-status'),source=document.getElementById('news-source'),tabs=document.getElementById('news-topics');
  let topic='all',articles=[],request=0,controller;
  const date=value=>new Intl.DateTimeFormat('ko-KR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
  function renderArticles(){
    list.replaceChildren();
    const filtered=articles.filter(a=>!source.value||a.source===source.value);
    for(const article of filtered){
      let url;try{url=new URL(article.url);}catch{continue;}
      if(url.protocol!=='https:'||!Number.isFinite(Date.parse(article.publishedAt)))continue;
      const link=document.createElement('a');link.className='press-card article-row';link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';
      const body=document.createElement('div'),meta=document.createElement('small'),title=document.createElement('h3'),arrow=document.createElement('span');
      meta.textContent=article.source+' · '+date(article.publishedAt);title.textContent=article.title;arrow.textContent='↗';body.append(meta,title);link.append(body,arrow);list.append(link);
    }
    if(!list.children.length)list.textContent='선택한 조건에 해당하는 기사가 없습니다.';
  }
  function renderVideos(){
    const label=topics.find(t=>t[0]===topic)[1];
    document.getElementById('video-list').innerHTML=['CNBC','Yahoo Finance','Wall Street Journal'].map((name,i)=>`<a class="video-card" href="https://www.youtube.com/results?search_query=${encodeURIComponent(name+' '+queries[topic])}" target="_blank" rel="noopener noreferrer"><div class="video-art art-${i}"><span>${name.toUpperCase()}</span><b>▶</b><small>${label} / VIDEO SEARCH ↗</small></div><h3>${name} · ${label} 영상</h3><p>YouTube에서 관련 영상 찾기 ↗</p></a>`).join('');
  }
  async function load(){
    const id=++request;controller?.abort();controller=new AbortController();const signal=controller.signal;
    tabs.innerHTML=topics.map(([key,label])=>`<button data-topic="${key}" aria-pressed="${key===topic}">${label}</button>`).join('');
    status.textContent='기사를 불러오는 중입니다…';list.setAttribute('aria-busy','true');list.replaceChildren();source.disabled=true;renderVideos();
    const timeout=setTimeout(()=>controller?.signal===signal&&controller.abort(),25000);
    try{
      let data,fallback=false;
      try{const response=await fetch('/api/news?topic='+topic,{signal,cache:'no-store'});if(!response.ok)throw Error('API');data=await response.json();if(!Array.isArray(data.articles))throw Error('schema');}
      catch(error){if(id!==request)return;const response=await fetch('market-news-snapshot.json',{cache:'no-store'});if(!response.ok)throw error;data=(await response.json())[topic];fallback=true;}
      if(id!==request)return;
      if(!data||!Array.isArray(data.articles))throw Error('schema');articles=data.articles;
      const previous=source.value;source.replaceChildren(new Option('전체 매체',''));[...new Set(articles.map(a=>a.source))].sort().forEach(name=>source.add(new Option(name,name)));source.value=[...source.options].some(o=>o.value===previous)?previous:'';
      status.textContent=`${fallback?'저장된 기사 · API 연결 불가':data.stale?'갱신 지연 · 마지막 수집 기사':'API 연결됨 · 10분 캐시'} · 수집 ${date(data.updatedAt)} · ${articles.length}건`;
      renderArticles();
    }catch(error){if(id===request){articles=[];status.textContent='뉴스를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.';list.textContent='뉴스 제공 서비스에 연결할 수 없습니다.';}}
    finally{clearTimeout(timeout);if(id===request){list.setAttribute('aria-busy','false');source.disabled=false;}}
  }
  tabs.onclick=e=>{const button=e.target.closest('[data-topic]');if(button){topic=button.dataset.topic;load();}};source.onchange=renderArticles;document.getElementById('news-refresh').onclick=load;load();
})();
