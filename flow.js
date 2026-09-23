(() => {
  function flowing(container, cards, selectable = false, onSelect = null, initialIndex = 0) {
    let index=initialIndex,position=initialIndex,manual=null;
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const viewport=document.createElement('div');viewport.className='coverflow continuous-flow';viewport.tabIndex=0;viewport.setAttribute('aria-label','카드 탐색 · 좌우 방향키로 이동');
    const status=document.createElement('p');status.className='coverflow-status';
    cards.forEach((card,i)=>{card.classList.add('coverflow-card');if(selectable)card.addEventListener('click',()=>{if(onSelect)onSelect(i);else move(i-index);});viewport.append(card);});
    function render(){
      cards.forEach((card,i)=>{let offset=((i-position)%cards.length+cards.length)%cards.length;if(offset>cards.length/2)offset-=cards.length;const distance=Math.abs(offset);card.style.setProperty('--offset',offset);card.style.setProperty('--distance',distance);card.style.zIndex=String(100-Math.round(distance*10));card.classList.toggle('is-current',i===index);card.style.visibility=distance>3?'hidden':'visible';card.inert=selectable?distance>3:i!==index;card.setAttribute('aria-hidden',String(selectable?distance>3:i!==index));if(selectable)card.setAttribute('aria-pressed',String(i===index));});
      status.textContent=String(index+1).padStart(2,'0')+' / '+String(cards.length).padStart(2,'0');
    }
    let frame,previousTime=null;
    function tick(now){
      const elapsed=previousTime===null?0:Math.min(now-previousTime,50);previousTime=now;
      if(!document.hidden){
        if(manual){
          const t=Math.min(1,(now-manual.start)/1200);
          const eased=t*t*(3-2*t);
          position=manual.from+(manual.to-manual.from)*eased;
          if(t===1)manual=null;
        }else if(!reduced.matches){position+=elapsed/6500;}
        position=(position+cards.length)%cards.length;
        index=Math.round(position)%cards.length;render();
      }
      frame=requestAnimationFrame(tick);
    }
    function move(step){
      if(onSelect){onSelect((index+step+cards.length)%cards.length);return;}
      focusCard(index+step);
    }
    function focusCard(destination){
      while(destination-position>cards.length/2)destination-=cards.length;
      while(destination-position<-cards.length/2)destination+=cards.length;
      if(reduced.matches){position=(destination+cards.length)%cards.length;index=Math.round(position)%cards.length;render();}
      else manual={from:position,to:destination,start:performance.now()};
    }
    viewport.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();move(e.key==='ArrowLeft'?-1:1);}};
    let touchX=null;viewport.addEventListener('touchstart',e=>{touchX=e.touches[0].clientX;},{passive:true});viewport.addEventListener('touchend',e=>{if(touchX!==null){const dx=e.changedTouches[0].clientX-touchX;if(Math.abs(dx)>45)move(dx<0?1:-1);touchX=null;}},{passive:true});
    container.append(viewport,status);render();frame=requestAnimationFrame(tick);
    // Cancel an old carousel when refreshed quote data replaces its DOM.
    const observer=new MutationObserver(()=>{if(!viewport.isConnected){cancelAnimationFrame(frame);observer.disconnect();}});observer.observe(container,{childList:true});
    return focusCard;
  }
  const macro=document.querySelector('.macro-grid');
  if(macro){const cards=[...macro.children].map(original=>{const card=document.createElement('button');card.type='button';card.className='macro-flow-card';card.setAttribute('aria-label',original.firstElementChild.textContent+' 카드 선택');card.append(...original.childNodes);original.remove();return card;});macro.removeAttribute('style');macro.className='market-flow';flowing(macro,cards,true);}
  const today=document.getElementById('today-flow');
  if(today){
    let signature='',focusCard;
    function render(force=false){const selection=window.TodaySelection;const key=selection.tickers.join(',');if(!force&&signature===key){focusCard(selection.index);return;}signature=key;today.replaceChildren();const cards=selection.tickers.map(ticker=>window.StockData.stocks.find(s=>s.ticker===ticker)).map(s=>{
      const card=document.createElement('button');card.type='button';card.className='flow-stock';card.setAttribute('aria-label',s.name+' 선택');
      card.innerHTML=`<div class="flow-stock-heading"><img src="logos/${s.ticker.toLowerCase()}.png" alt=""><span><small>${s.ticker}</small><strong>${s.name}</strong></span><span class="flow-arrow">↗</span></div><small>현재주가</small><div class="flow-price">${s.price}<span class="${s.change>=0?'up':'down'}">${s.change>=0?'+':''}${s.change.toFixed(2)}%</span></div><div class="flow-score"><span>매력도지수</span><b>산정 전</b></div><div class="flow-score"><span>참고 재무점수</span><b>${s.score==null?'미평가':s.score.toFixed(1)}</b></div>`;return card;});focusCard=flowing(today,cards,true,i=>window.selectTodayStock(selection.tickers[i]),selection.index);}
    render();window.addEventListener('today-selection',()=>render());window.addEventListener('quotes-updated',()=>render(true));
  }
})();
