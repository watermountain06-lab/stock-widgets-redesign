window.Reading = {
  load(page) {
    try { return JSON.parse(localStorage.getItem('stock-reading-'+page)) || {}; } catch { return {}; }
  },
  bind(page, getState, restoreY) {
    let ready=false, timer;
    const save=()=>{if(!ready)return;try{localStorage.setItem('stock-reading-'+page,JSON.stringify({...getState(),y:scrollY}));}catch{}};
    const initialize=()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(Number.isFinite(restoreY)&&restoreY>=0)scrollTo({top:restoreY,behavior:'instant'});
      ready=true;save();
    }));
    if(document.readyState==='complete')initialize();else window.addEventListener('load',initialize,{once:true});
    window.addEventListener('scroll',()=>{clearTimeout(timer);timer=setTimeout(save,150);},{passive:true});
    window.addEventListener('pagehide',save);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)save();});
    return save;
  }
};
