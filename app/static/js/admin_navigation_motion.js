(() => {
  'use strict';
  if (window.dnAdminMotion) return;

  const GSAP_URL = 'https://cdn.jsdelivr.net/npm/gsap@3.14.1/dist/gsap.min.js';
  const STORAGE_KEY = 'dn-admin-motion-navigation';
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let currentRoot = null;
  let entryContext = null;
  let progressTween = null;
  let progressNode = null;
  let libraryPromise = null;
  let entryGeneration = 0;

  function getRoot() {
    return document.querySelector('[data-admin-app]');
  }

  function loadGSAP() {
    if (window.gsap) return Promise.resolve(window.gsap);
    if (libraryPromise) return libraryPromise;
    libraryPromise = new Promise(resolve => {
      let finished = false;
      let timer;
      const finish = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        resolve(window.gsap || null);
      };
      timer = setTimeout(finish, 700);
      let script = document.querySelector('script[src*="gsap"][src*="gsap.min.js"]');
      const isNew = !script;
      if (isNew) {
        script = document.createElement('script');
        script.src = GSAP_URL;
        script.async = true;
        script.dataset.adminMotionGsap = 'true';
      }
      script.addEventListener('load', finish, { once:true });
      script.addEventListener('error', finish, { once:true });
      if (isNew) document.head.appendChild(script);
    });
    return libraryPromise;
  }

  function clearEntry() {
    if (entryContext) entryContext.revert();
    entryContext = null;
  }

  function clearProgress() {
    if (progressTween) progressTween.kill();
    progressTween = null;
    if (progressNode) progressNode.remove();
    progressNode = null;
    document.querySelectorAll('.dn-admin-motion-pending').forEach(link => {
      link.classList.remove('dn-admin-motion-pending');
    });
  }

  function consumeNavigation() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      sessionStorage.removeItem(STORAGE_KEY);
      if (!raw) return false;
      const data = JSON.parse(raw);
      return data.target === location.pathname + location.search
        && Date.now() - data.at < 15000;
    } catch (_) { return false; }
  }

  async function animate(root, workspaceOnly = false) {
    const generation = ++entryGeneration;
    const started = performance.now();
    clearEntry();
    if (!root || reducedMotion.matches) return;
    const navigated = workspaceOnly ? false : consumeNavigation();
    const library = await loadGSAP();
    if (!library || reducedMotion.matches || !root.isConnected
        || generation !== entryGeneration || performance.now() - started > 650) return;

    const context = root.querySelector('.dn-admin-context');
    const workspace = root.querySelector('#admin-workspace');
    const active = root.querySelectorAll(
      '.dn-admin-sidebar a.is-active, .dn-admin-mobile-nav a.is-active'
    );
    const inventory = root.dataset.activeSection === 'inventory';
    entryContext = library.context(() => {
      const timeline = library.timeline({ defaults:{ ease:'power2.out' } });
      if (!workspaceOnly && context) {
        timeline.from(context, {
          y:navigated ? 16 : 10, opacity:0,
          duration:.28, clearProps:'transform,opacity'
        });
      }
      // Inventario ya anima sus resultados: no duplicar ese efecto.
      if (workspace && !inventory) {
        timeline.from(workspace, {
          y:navigated ? 20 : 12, opacity:0,
          duration:.34, clearProps:'transform,opacity'
        }, workspaceOnly ? 0 : .06);
      }
      if (!workspaceOnly && active.length) {
        timeline.from(active, {
          x:4, duration:.25, clearProps:'transform'
        }, 0);
      }
    }, root);
  }

  function initialize() {
    const root = getRoot();
    if (!root || root === currentRoot) return;
    currentRoot = root;
    clearProgress();
    animate(root);
  }

  function showProgress(link) {
    clearProgress();
    if (reducedMotion.matches) return;
    const root = getRoot();
    if (!root) return;
    link.classList.add('dn-admin-motion-pending');
    const node = document.createElement('div');
    node.className = 'dn-admin-motion-progress';
    node.setAttribute('role', 'status');
    const bar = document.createElement('span');
    bar.className = 'dn-admin-motion-progress-bar';
    bar.setAttribute('aria-hidden', 'true');
    const status = document.createElement('span');
    status.className = 'dn-admin-motion-status';
    status.textContent = 'Abriendo ' + link.textContent.trim().replace(/\s+/g, ' ');
    node.append(bar, status);
    root.appendChild(node);
    progressNode = node;
    if (window.gsap) {
      progressTween = window.gsap.fromTo(bar, { xPercent:-110 }, {
        xPercent:290, duration:.85, ease:'none', repeat:-1
      });
    }
    setTimeout(() => { if (progressNode === node) clearProgress(); }, 8000);
  }

  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0
        || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest(
      '.dn-admin-sidebar a[href], .dn-admin-mobile-nav a[href]'
    );
    if (!link || !link.closest('[data-admin-app]')
        || link.hasAttribute('download') || link.getAttribute('aria-disabled') === 'true'
        || link.classList.contains('is-disabled')
        || (link.target && link.target !== '_self')) return;
    const href = link.getAttribute('href');
    if (!href || href.startsWith('#')) return;
    // No alterar enlaces que ya tengan navegación AJAX asignada.
    if (link.closest('[hx-get], [data-hx-get], [hx-boost], [data-hx-boost]')) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin
        || !['http:', 'https:'].includes(target.protocol)
        || target.pathname + target.search === location.pathname + location.search) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        target:target.pathname + target.search, at:Date.now()
      }));
    } catch (_) {}
    showProgress(link);
    // Sin preventDefault ni timeout: el navegador sigue inmediatamente el href.
  });

  document.addEventListener('htmx:beforeCleanupElement', event => {
    const element = event.detail && event.detail.elt;
    if (element && currentRoot
        && (element === currentRoot || element.contains(currentRoot))) {
      ++entryGeneration;
      clearEntry();
      clearProgress();
      currentRoot = null;
    }
  });
  document.addEventListener('htmx:afterSwap', event => {
    const root = getRoot();
    if (root !== currentRoot) { initialize(); return; }
    const target = event.detail && event.detail.target;
    if (root && target && target.id === 'admin-workspace') animate(root, true);
    // Filtros, tablas y detalles internos conservan sus propios efectos.
  });
  window.addEventListener('pagehide', () => {
    ++entryGeneration;
    clearEntry();
    clearProgress();
  });
  window.addEventListener('pageshow', event => {
    clearProgress();
    if (event.persisted) { currentRoot = null; initialize(); }
  });
  reducedMotion.addEventListener('change', () => {
    ++entryGeneration;
    clearEntry();
    clearProgress();
  });

  window.dnAdminMotion = { initialize };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once:true });
  } else initialize();
})();
