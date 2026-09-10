// Shared carousel interactions. Vertical scrolling and controls keep native behavior.
window.bindCardNavigation = function(stage, move) {
  stage.tabIndex = 0;
  stage.setAttribute('aria-label', '종목 카드 · 좌우 방향키 또는 좌우로 밀어서 이동');
  stage.style.touchAction = 'pan-y';
  const interactive = target => target.closest('a,button,input,select,textarea,summary,[contenteditable]');
  stage.addEventListener('keydown', event => {
    if (interactive(event.target) || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault(); move(event.key === 'ArrowRight' ? 1 : -1);
    }
  });
  let start;
  stage.addEventListener('pointerdown', event => {
    if (event.pointerType !== 'touch' || interactive(event.target)) return;
    start = {x:event.clientX, y:event.clientY, id:event.pointerId};
  });
  stage.addEventListener('pointerup', event => {
    if (!start || start.id !== event.pointerId) return;
    const dx=event.clientX-start.x, dy=event.clientY-start.y; start=null;
    if (Math.abs(dx)>55 && Math.abs(dx)>Math.abs(dy)*1.5) move(dx<0?1:-1);
  });
  stage.addEventListener('pointercancel', ()=>{start=null;});
};
