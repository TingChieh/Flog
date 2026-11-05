document.addEventListener('DOMContentLoaded', () => {
  const navToggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-site-nav]');
  const backToTop = document.querySelector('[data-back-to-top]');
  const adminDrawerToggle = document.querySelector('[data-admin-drawer-toggle]');
  const adminDrawer = document.querySelector('[data-admin-drawer]');
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');

  navToggle?.addEventListener('click', () => {
    const open = nav.hidden;
    nav.hidden = !open;
    nav.classList.toggle('site-nav__menu--open', open);
    navToggle.setAttribute('aria-expanded', String(open));
  });

  const setAdminDrawerOpen = (open, returnFocus = false) => {
    if (!adminDrawer || !adminDrawerToggle) return;
    adminDrawer.classList.toggle('admin-drawer--open', open);
    adminDrawerToggle.setAttribute('aria-expanded', String(open));
    if (returnFocus) adminDrawerToggle.focus();
  };

  adminDrawerToggle?.addEventListener('click', () => {
    setAdminDrawerOpen(!adminDrawer?.classList.contains('admin-drawer--open'));
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !event.defaultPrevented && nav && !nav.hidden) {
      nav.hidden = true;
      nav.classList.remove('site-nav__menu--open');
      navToggle.setAttribute('aria-expanded', 'false');
      navToggle.focus();
    }
    if (event.key === 'Escape' && adminDrawer?.classList.contains('admin-drawer--open')) {
      setAdminDrawerOpen(false, true);
    }
  });

  const syncBackToTop = () => {
    if (!backToTop) return;
    backToTop.hidden = scrollY <= innerHeight;
  };
  addEventListener('scroll', syncBackToTop, {passive: true});
  syncBackToTop();

  backToTop?.addEventListener('click', () => {
    scrollTo({top: 0, behavior: reduceMotion.matches ? 'auto' : 'smooth'});
  });
});
