(() => {
  const root = document.documentElement;
  const key = 'organiza.appearance';
  let theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  try {
    const saved = localStorage.getItem(key);
    if (saved === 'light' || saved === 'dark') theme = saved;
  } catch {
    // Browser storage can be unavailable.
  }

  function labelButtons() {
    const label = theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro';
    for (const button of document.querySelectorAll('[data-theme-toggle]')) {
      if (button.title !== label) button.title = label;
      if (button.getAttribute('aria-label') !== label) button.setAttribute('aria-label', label);
    }
  }

  function apply() {
    root.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#111b17' : '#163e36';
    labelButtons();
  }

  apply();
  document.addEventListener('DOMContentLoaded', () => {
    labelButtons();
    const app = document.getElementById('app');
    new MutationObserver(labelButtons).observe(app, {childList:true, subtree:true});
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-theme-toggle]')) return;
    theme = theme === 'dark' ? 'light' : 'dark';
    try {
      localStorage.setItem(key, theme);
    } catch {
      // Retain the choice for the current page.
    }
    apply();
  });
})();
