(() => {
  const preference = matchMedia('(prefers-color-scheme: dark)');
  let choice = null;
  try { choice = localStorage.getItem('site-theme'); } catch {}
  if (!['light', 'dark'].includes(choice)) choice = null;
  function apply() {
    const dark = choice ? choice === 'dark' : preference.matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.setAttribute('aria-checked', String(dark));
      toggle.title = dark ? '라이트 모드로 전환' : '다크 모드로 전환';

    }
  }
  function save(value) {
    choice = value;
    try { value ? localStorage.setItem('site-theme', value) : localStorage.removeItem('site-theme'); } catch {}
    apply();
  }
  apply();
  preference.addEventListener('change', apply);
  window.addEventListener('storage', e => {
    if (e.key === 'site-theme' || e.key === null) {
      choice = ['light', 'dark'].includes(e.newValue) ? e.newValue : null;
      apply();
    }
  });
  document.addEventListener('DOMContentLoaded', () => {
    const header = document.querySelector('.site-header .header-inner');
    if (!header) return;
    const controls = document.createElement('div');
    controls.className = 'theme-controls';
    controls.innerHTML = '<button id="theme-toggle" type="button" role="switch" aria-label="다크 모드" aria-checked="false"><span aria-hidden="true">☀</span><span class="theme-knob" aria-hidden="true"></span><span aria-hidden="true">☾</span></button>';
    header.querySelector('nav').prepend(controls);
    document.getElementById('theme-toggle').onclick = () => save(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

    apply();
  });
})();

