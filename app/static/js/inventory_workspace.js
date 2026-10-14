(() => {
  if (window.dnInventoryUI) {
    window.dnInventoryUI.initialize();
    return;
  }

  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const contexts = new Map();
  let initializedRoot = null;

  function dispose(element) {
    contexts.forEach((context, root) => {
      if (root === element || element.contains(root)) {
        context.revert();
        contexts.delete(root);
      }
    });
  }

  function animateResults(initial) {
    const root = document.getElementById('inventory-results');
    if (!root) return;
    dispose(root);
    if (!window.gsap || motion.matches) return;
    const viewportHeight = window.innerHeight;
    const visible = [...root.querySelectorAll('[data-inventory-card]')].filter(card => {
      const box = card.getBoundingClientRect();
      return box.top < viewportHeight + 100 && box.bottom > 0;
    });
    const context = gsap.context(() => {
      const timeline = gsap.timeline({ defaults: { ease: 'power3.out' } });
      timeline.from(root.querySelectorAll('[data-inventory-metric]'), {
        y: 18, opacity: 0, duration: .45, stagger: .06, clearProps: 'transform,opacity'
      });
      if (visible.length) timeline.from(visible, {
        y: initial ? 32 : 18, opacity: 0, scale: .98,
        duration: .55, stagger: .07, clearProps: 'transform,opacity'
      }, '-=.2');
    }, root);
    contexts.set(root, context);
  }

  function animateDetail(slot) {
    dispose(slot);
    if (!window.gsap || motion.matches || !slot.children.length) return;
    const context = gsap.context(() => {
      const height = slot.scrollHeight;
      gsap.timeline({ defaults: { ease: 'power2.out' } })
        .fromTo(slot, { height: 0, overflow: 'hidden' }, {
          height, duration: .38, clearProps: 'height,overflow'
        })
        .from(slot.querySelector('[data-inventory-detail]'), {
          y: 14, opacity: 0, duration: .3, clearProps: 'transform,opacity'
        }, '-=.22');
    }, slot);
    contexts.set(slot, context);
  }

  function requestError(message) {
    const node = document.getElementById('inventory-request-error');
    if (node) { node.textContent = message; node.hidden = false; }
  }

  function initialize() {
    const root = document.getElementById('inventory-workspace');
    if (!root || root === initializedRoot) return;
    initializedRoot = root;
    animateResults(true);
  }

  document.addEventListener('error', event => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.hasAttribute('data-inventory-image')) return;
    image.hidden = true;
    const fallback = image.parentElement.querySelector('.dn-inventory-photo-fallback');
    if (fallback) { fallback.hidden = false; fallback.textContent = 'Foto no disponible'; }
  }, true);

  document.addEventListener('click', event => {
    const close = event.target.closest('[data-inventory-close]');
    if (!close) return;
    const slot = close.closest('[data-inventory-detail-slot]');
    if (!slot) return;
    const card = slot.closest('[data-inventory-card]');
    const opener = card.querySelector('[data-inventory-open]');
    dispose(slot);
    const finish = () => {
      slot.replaceChildren();
      slot.style.removeProperty('height');
      slot.style.removeProperty('overflow');
      opener.setAttribute('aria-expanded', 'false');
      opener.focus({ preventScroll: true });
    };
    if (window.gsap && !motion.matches) {
      close.disabled = true;
      gsap.to(slot, { height: 0, overflow: 'hidden', duration: .28,
        ease: 'power2.inOut', onComplete: finish });
    } else finish();
  });

  document.body.addEventListener('htmx:beforeRequest', event => {
    if (!event.detail.elt.closest('#inventory-workspace')) return;
    const error = document.getElementById('inventory-request-error');
    if (error) error.hidden = true;
    const target = event.detail.target;
    if (target && target.hasAttribute('data-inventory-detail-slot')) dispose(target);
  });

  document.body.addEventListener('htmx:beforeSwap', event => {
    if (event.detail.target && event.detail.target.id === 'inventory-results'
        && event.detail.xhr.status >= 200 && event.detail.xhr.status < 300) {
      dispose(event.detail.target);
    }
  });

  document.body.addEventListener('htmx:beforeCleanupElement', event => {
    const element = event.detail.elt;
    if (element) dispose(element);
    if (element === initializedRoot) initializedRoot = null;
  });

  document.body.addEventListener('htmx:afterSwap', event => {
    const target = event.detail.target;
    initialize();
    if (target && target.id === 'inventory-results') animateResults(false);
    if (target && target.hasAttribute('data-inventory-detail-slot')) {
      const opener = target.closest('[data-inventory-card]').querySelector('[data-inventory-open]');
      opener.setAttribute('aria-expanded', 'true');
      animateDetail(target);
    }
  });

  document.body.addEventListener('htmx:responseError', event => {
    if (event.detail.elt.closest('#inventory-workspace')) requestError(
      'No fue posible actualizar el inventario. Revisa tu sesión e intenta nuevamente.'
    );
  });
  document.body.addEventListener('htmx:sendError', event => {
    if (event.detail.elt.closest('#inventory-workspace')) requestError('Sin conexión con el servidor.');
  });
  motion.addEventListener('change', () => {
    if (motion.matches) contexts.forEach(context => context.revert());
    if (motion.matches) contexts.clear();
  });
  window.dnInventoryUI = { initialize };
  initialize();
})();
