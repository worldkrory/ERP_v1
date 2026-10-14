(() => {
  'use strict';
  if (window.dnMobilePolish) return;
  const mobile = window.matchMedia('(max-width: 980px)');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const labels = {
    'resumen':'home', 'terceros':'parties', 'origen y compras':'purchases',
    'inventario':'inventory', 'produccion':'production', 'ventas':'sales',
    'despacho':'dispatch', 'recaudo':'collections', 'balances':'balances',
    'reportes':'reports', 'trazabilidad':'traceability'
  };
  let state = null;
  let gsapPromise = null;

  function loadGSAP() {
    if (window.gsap) return Promise.resolve(window.gsap);
    if (gsapPromise) return gsapPromise;
    gsapPromise = new Promise(resolve => {
      let finished = false;
      let timer;
      const finish = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        resolve(window.gsap || null);
      };
      timer = setTimeout(finish, 800);
      let script = document.querySelector('script[src*="gsap"][src*="gsap.min.js"]');
      const isNew = !script;
      if (isNew) {
        script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/gsap@3.14.1/dist/gsap.min.js';
        script.async = true;
      }
      script.addEventListener('load', finish, { once:true });
      script.addEventListener('error', finish, { once:true });
      if (isNew) document.head.appendChild(script);
    });
    return gsapPromise;
  }

  function closeMenu() {
    if (document.body.classList.contains('dn-admin-menu-open')) {
      document.body.classList.remove('dn-admin-menu-open');
    }
    document.querySelectorAll('[data-admin-menu-toggle]').forEach(button => {
      button.setAttribute('aria-expanded', 'false');
    });
  }

  function clearAnimations() {
    if (!state) return;
    if (state.entry) state.entry.revert();
    if (state.drawer) state.drawer.revert();
    state.entry = state.drawer = null;
    if (window.gsap) {
      const icons = [...state.bar.querySelectorAll('.dn-mobile-icon')];
      window.gsap.killTweensOf(icons);
      window.gsap.set(icons, { clearProps:'transform' });
    }
  }

  function updateIcons() {
    if (!state) return;
    state.originals.forEach((original, node) => {
      if (!mobile.matches) { node.innerHTML = original; return; }
      const label = node.nextElementSibling;
      const key = label && labels[label.textContent.trim().toLowerCase()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')];
      const template = key && state.bar.querySelector(`template[data-dn-icon="${key}"]`);
      if (template) node.replaceChildren(template.content.cloneNode(true));
    });
  }

  function syncMenu(animate = true) {
    if (!state) return;
    const open = mobile.matches && document.body.classList.contains('dn-admin-menu-open');
    state.scrim.hidden = !open;
    if (state.sidebar) {
      state.sidebar.inert = mobile.matches ? !open : state.sidebarInert;
      if (mobile.matches) state.sidebar.setAttribute('aria-hidden', String(!open));
      else if (state.sidebarHidden === null) state.sidebar.removeAttribute('aria-hidden');
      else state.sidebar.setAttribute('aria-hidden', state.sidebarHidden);
    }
    if (state.main) state.main.inert = open || state.mainInert;
    if (state.open === open) return;
    state.open = open;
    if (state.drawer) state.drawer.revert();
    state.drawer = null;
    if (open && animate && window.gsap && !reduced.matches && state.sidebar) {
      state.drawer = window.gsap.context(() => {
        window.gsap.from(state.sidebar.querySelectorAll('.dn-admin-nav-link'), {
          y:8, opacity:0, duration:.24, stagger:.025, ease:'power2.out',
          clearProps:'transform,opacity'
        });
      }, state.sidebar);
    }
  }

  function cleanup() {
    if (!state) return;
    state.observer.disconnect();
    clearAnimations();
    state.originals.forEach((original, node) => { node.innerHTML = original; });
    if (state.sidebar) {
      state.sidebar.inert = state.sidebarInert;
      if (state.sidebarHidden === null) state.sidebar.removeAttribute('aria-hidden');
      else state.sidebar.setAttribute('aria-hidden', state.sidebarHidden);
    }
    if (state.main) state.main.inert = state.mainInert;
    state.root.classList.remove('dn-mobile-polish');
    state = null;
  }

  async function initialize() {
    const root = document.querySelector('[data-admin-app]');
    const bar = root && root.querySelector('[data-dn-mobile-nav]');
    if (!bar || (state && state.root === root)) return;
    cleanup();
    const sidebar = root.querySelector('.dn-admin-sidebar');
    const main = root.querySelector('.dn-admin-main');
    const scrim = root.querySelector('[data-dn-mobile-scrim]');
    if (!scrim) return;
    state = { root, bar, sidebar, main, scrim, open:null, entry:null, drawer:null,
      sidebarInert:sidebar ? sidebar.inert : false,
      sidebarHidden:sidebar ? sidebar.getAttribute('aria-hidden') : null,
      mainInert:main ? main.inert : false, originals:new Map(), observer:null };
    root.querySelectorAll('.dn-admin-sidebar .dn-admin-nav-icon').forEach(node => {
      state.originals.set(node, node.innerHTML);
    });
    root.classList.add('dn-mobile-polish');
    updateIcons();
    state.observer = new MutationObserver(() => syncMenu());
    state.observer.observe(document.body, { attributes:true, attributeFilter:['class'] });
    syncMenu(false);
    if (!mobile.matches || reduced.matches) return;
    const started = performance.now();
    const thisState = state;
    const library = await loadGSAP();
    if (!library || state !== thisState || !mobile.matches || reduced.matches
        || performance.now() - started > 650) return;
    state.entry = library.context(() => {
      library.from(bar, { y:12, opacity:0, duration:.32,
        ease:'power2.out', clearProps:'transform,opacity' });
    }, root);
  }

  document.addEventListener('pointerdown', event => {
    if (!state || !mobile.matches || reduced.matches || !window.gsap) return;
    const target = event.target.closest('[data-dn-mobile-nav] > a, [data-dn-mobile-nav] > button');
    const icon = target && target.querySelector('.dn-mobile-icon');
    if (icon) window.gsap.to(icon, { scale:.88, duration:.09, overwrite:true });
  });
  function releaseIcons() {
    if (!state || !window.gsap) return;
    const icons = [...state.bar.querySelectorAll('.dn-mobile-icon')];
    if (reduced.matches) {
      window.gsap.killTweensOf(icons);
      window.gsap.set(icons, { clearProps:'transform' });
    } else window.gsap.to(icons, { scale:1, duration:.18, ease:'power2.out', overwrite:true,
      onComplete:() => window.gsap.set(icons, { clearProps:'transform' }) });
  }
  document.addEventListener('pointerup', releaseIcons);
  document.addEventListener('pointercancel', releaseIcons);
  document.addEventListener('click', event => {
    if (event.target.closest('[data-dn-mobile-scrim]')) closeMenu();
  });
  document.addEventListener('htmx:beforeCleanupElement', event => {
    const element = event.detail && event.detail.elt;
    if (state && element && (element === state.root || element.contains(state.root))) cleanup();
  });
  document.addEventListener('htmx:afterSwap', initialize);
  mobile.addEventListener('change', () => {
    if (!state) return;
    clearAnimations();
    if (!mobile.matches) closeMenu();
    updateIcons();
    syncMenu(false);
    if (mobile.matches && !reduced.matches) loadGSAP();
  });
  reduced.addEventListener('change', () => { clearAnimations(); syncMenu(false); });
  window.addEventListener('pagehide', clearAnimations);
  window.addEventListener('pageshow', () => {
    initialize();
    if (state) syncMenu(false);
  });
  window.dnMobilePolish = { initialize };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once:true });
  else initialize();
})();
