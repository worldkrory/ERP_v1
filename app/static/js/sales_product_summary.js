(() => {
  'use strict';
  if (window.dnSaleProductsUI) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const contexts = new Map();
  let libraryPromise = null;

  function loadGSAP() {
    if (window.gsap) return Promise.resolve(window.gsap);
    if (libraryPromise) return libraryPromise;
    libraryPromise = new Promise(resolve => {
      let done = false;
      let timer;
      const finish = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(window.gsap || null);
      };
      timer = setTimeout(finish, 700);
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
    return libraryPromise;
  }

  function cleanup(element) {
    contexts.forEach((context, root) => {
      if (root === element || element.contains(root)) {
        context.revert();
        contexts.delete(root);
      }
    });
  }

  function imageFallback(image) {
    image.hidden = true;
    const placeholder = image.parentElement.querySelector('.dn-sale-product-placeholder');
    if (placeholder) placeholder.hidden = false;
  }

  function checkImages(root) {
    root.querySelectorAll('[data-sale-product-image]').forEach(image => {
      if (image.complete && image.naturalWidth === 0) imageFallback(image);
    });
  }

  async function animateRows(root) {
    cleanup(root);
    if (reduced.matches) return;
    const started = performance.now();
    const library = await loadGSAP();
    if (!library || !root.isConnected || reduced.matches || performance.now() - started > 650) return;
    const rows = [...root.querySelectorAll('[data-sale-summary-row]')].filter(row => {
      const rect = row.getBoundingClientRect();
      return rect.bottom > 0 && rect.top < window.innerHeight;
    }).slice(0, 10);
    if (!rows.length) return;
    const context = library.context(() => {
      library.from(rows, { y:9, opacity:0, duration:.26, stagger:.025,
        ease:'power2.out', clearProps:'transform,opacity' });
    }, root);
    contexts.set(root, context);
  }

  function feedback(message) {
    const node = document.getElementById('sales-filter-feedback');
    if (node) { node.textContent = message; node.hidden = !message; }
  }

  document.addEventListener('error', event => {
    const image = event.target;
    if (image instanceof HTMLImageElement && image.hasAttribute('data-sale-product-image')) imageFallback(image);
  }, true);

  document.addEventListener('toggle', async event => {
    const details = event.target;
    if (!(details instanceof HTMLElement) || !details.hasAttribute('data-sale-products-more')) return;
    cleanup(details);
    if (!details.open || reduced.matches) return;
    const started = performance.now();
    const library = await loadGSAP();
    if (!library || !details.isConnected || !details.open || reduced.matches
        || performance.now() - started > 650) return;
    const context = library.context(() => {
      library.from(details.querySelectorAll('.dn-sale-products-extra .dn-sale-product-line'), {
        y:6, opacity:0, duration:.2, stagger:.025,
        ease:'power2.out', clearProps:'transform,opacity'
      });
    }, details);
    contexts.set(details, context);
  }, true);

  document.addEventListener('htmx:beforeRequest', event => {
    if (event.detail.target && event.detail.target.id === 'sales-results') feedback('');
  });
  document.addEventListener('htmx:beforeSwap', event => {
    const target = event.detail.target;
    if (!target || target.id !== 'sales-results') return;
    if (event.detail.xhr.status >= 200 && event.detail.xhr.status < 300) {
      const documentResponse = new DOMParser().parseFromString(event.detail.xhr.responseText, 'text/html');
      if (!documentResponse.getElementById('sales-results')) {
        event.detail.shouldSwap = false;
        feedback('La respuesta no contiene la bandeja. Revisa tu sesión o recarga la página.');
        return;
      }
      cleanup(target);
    }
  });
  document.addEventListener('htmx:beforeCleanupElement', event => {
    if (event.detail.elt) cleanup(event.detail.elt);
  });
  document.addEventListener('htmx:afterSwap', event => {
    const root = document.getElementById('sales-results');
    if (!root) return;
    const target = event.detail.target;
    if (target && (target === root || target.id === 'sales-results')) {
      checkImages(root);
      animateRows(root);
    }
  });
  document.addEventListener('htmx:responseError', event => {
    if (event.detail.target && event.detail.target.id === 'sales-results') feedback('No fue posible actualizar las ventas. Intenta nuevamente.');
  });
  document.addEventListener('htmx:sendError', event => {
    if (event.detail.target && event.detail.target.id === 'sales-results') feedback('No hay conexión con el servidor. Se conservan los resultados anteriores.');
  });
  reduced.addEventListener('change', () => {
    if (reduced.matches) cleanup(document.documentElement);
  });
  window.addEventListener('pagehide', () => cleanup(document.documentElement));
  window.dnSaleProductsUI = {};
  const root = document.getElementById('sales-results');
  if (root) {
    checkImages(root);
    if (!reduced.matches) loadGSAP();
  }
})();
