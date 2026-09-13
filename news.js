(() => {
 let request=0;
 const snapshot=fetch('news-snapshot.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('fetch');return r.json();});
 snapshot.catch(()=>{});
 const date=value=>new Intl.DateTimeFormat('ko-KR',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Seoul'}).format(new Date(value));
 window.renderNews=async ticker=>{
  const current=++request, list=document.getElementById('news-articles'), stamp=document.getElementById('news-updated');
  list.textContent='뉴스를 불러오는 중입니다…';stamp.textContent='';
  try{
   const data=await snapshot;if(current!==request)return;
   const articles=data.stocks?.[ticker];list.replaceChildren();
   if(!Array.isArray(articles)||!articles.length){list.textContent='표시할 뉴스가 없습니다. 아래 검색을 이용해 주세요.';return;}
   for(const article of articles.slice(0,3)){
    let url;try{url=new URL(article.url);}catch{continue;}
    if(url.protocol!=='https:'||!Number.isFinite(Date.parse(article.publishedAt)))continue;
    const link=document.createElement('a');link.className='news-article';link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';
    const title=document.createElement('strong');title.textContent=article.title;
    const meta=document.createElement('span');meta.textContent=article.source+' · '+date(article.publishedAt)+' KST';
    link.append(title,meta);list.append(link);
   }
   if(!list.children.length)list.textContent='표시할 뉴스가 없습니다.';
   stamp.textContent='수집: '+date(data.updatedAt)+' KST · 저장된 뉴스';
  }catch{if(current===request){list.textContent='뉴스를 불러오지 못했습니다. 아래 뉴스 검색을 이용해 주세요.';}}
 };
})();
