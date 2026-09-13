// Shared carousel interactions. Vertical scrolling and controls keep native behavior.
window.bindCardNavigation = function(stage, move) {
  stage.tabIndex = 0;
  stage.setAttribute('aria-label', '종목 카드 · 좌우 방향키 또는 좌우로 밀어서 이동');
  stage.style.touchAction = 'pan-y';
  stage.addEventListener('dragstart', event=>event.preventDefault());
  const interactive = target => target.closest('a,button,input,select,textarea,summary,[contenteditable]');
  stage.addEventListener('keydown', event => {
    if (interactive(event.target) || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault(); move(event.key === 'ArrowRight' ? 1 : -1);
    }
  });
  let gesture=null, suppressClickUntil=0;
  const card=()=>stage.querySelector('#story, #feature-card');
  const reset=()=>{const el=card();if(el){el.style.transform='';el.style.willChange='';el.style.userSelect='';}gesture=null;};
  stage.addEventListener('pointerdown', event => {
    if ((event.pointerType==='mouse' && event.button!==0) || event.isPrimary===false || event.target.closest('input,select,textarea,summary,[contenteditable]')) return;
    reset();
    gesture={x:event.clientX,y:event.clientY,id:event.pointerId,dragging:false};
  });
  stage.addEventListener('pointermove', event => {
    if(!gesture || gesture.id!==event.pointerId)return;
    const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
    if(!gesture.dragging){
      if(Math.abs(dy)>12 && Math.abs(dy)>Math.abs(dx)){reset();return;}
      if(Math.abs(dx)<12 || Math.abs(dx)<Math.abs(dy)*1.3)return;
      gesture.dragging=true;stage.setPointerCapture(event.pointerId);
    }
    event.preventDefault();
    const el=card();if(el){el.style.userSelect='none';el.style.willChange='transform';el.style.transform='translateX('+Math.max(-120,Math.min(120,dx*.65))+'px)';}
  });
  stage.addEventListener('pointerup', event => {
    if(!gesture || gesture.id!==event.pointerId)return;
    const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y,dragged=gesture.dragging;
    if(stage.hasPointerCapture(event.pointerId))stage.releasePointerCapture(event.pointerId);
    reset();
    if(dragged){
      suppressClickUntil=Date.now()+450;
      if(Math.abs(dx)>45 && Math.abs(dx)>Math.abs(dy)*1.3)move(dx<0?1:-1);
    }
  });
  stage.addEventListener('click', event=>{if(Date.now()<suppressClickUntil){event.preventDefault();event.stopImmediatePropagation();}},true);
  stage.addEventListener('pointercancel',reset);
  stage.addEventListener('lostpointercapture',reset);
};
