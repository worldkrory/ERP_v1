(() => {
  if (window.dnLotReports) { window.dnLotReports.initialize(); return; }

  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const contexts = new Map();
  let masked = false;
  let lastOpened = null;
  let initializedRoot = null;

  const nf = (digits) => new Intl.NumberFormat('es-CO', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const FORMAT = {
    money: v => (v < 0 ? '-' : '') + '$ ' + nf(0).format(Math.abs(v)),
    pct: v => nf(1).format(v * 100) + ' %',
    int: v => nf(0).format(v),
  };

  function dispose(element) {
    contexts.forEach((context, root) => {
      if (root === element || element.contains(root)) { context.revert(); contexts.delete(root); }
    });
  }

  function inView(node) {
    const box = node.getBoundingClientRect();
    return box.top < window.innerHeight + 100 && box.bottom > 0;
  }

  function animate(scope, first) {
    if (!scope) return;
    dispose(scope);
    if (!window.gsap || motion.matches) return;
    const context = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
      const header = scope.querySelector('.dn-lr-header');
      if (header) tl.from(header.children, { y: 16, opacity: 0, duration: .45, stagger: .08, clearProps: 'transform,opacity' });
      const metrics = [...scope.querySelectorAll('[data-lr-metric]')];
      if (metrics.length) tl.from(metrics, { y: 18, opacity: 0, duration: .45, stagger: .06, clearProps: 'transform,opacity' }, header ? '-=.25' : 0);
      const rows = [...scope.querySelectorAll('[data-lr-row]')].filter(inView).slice(0, 14);
      if (rows.length) tl.from(rows, { y: first ? 26 : 14, opacity: 0, duration: .4, stagger: .04, clearProps: 'transform,opacity' }, '-=.2');
      const panels = [...scope.querySelectorAll('[data-lr-panel]')].filter(inView).slice(0, 6);
      if (panels.length) tl.from(panels, { y: 22, opacity: 0, duration: .5, stagger: .07, clearProps: 'transform,opacity' }, '-=.25');
      const fills = [...scope.querySelectorAll('.dn-lr-fill')].filter(inView);
      if (fills.length) tl.from(fills, { scaleX: 0, duration: .8, ease: 'power2.out', stagger: .02, clearProps: 'transform' }, '-=.3');
      scope.querySelectorAll('[data-lr-line]').forEach(path => {
        if (typeof path.getTotalLength !== 'function') return;
        const length = path.getTotalLength();
        tl.fromTo(path, { strokeDasharray: length, strokeDashoffset: length },
          { strokeDashoffset: 0, duration: 1.1, ease: 'power2.inOut', clearProps: 'strokeDasharray,strokeDashoffset' }, '-=.6');
      });
      scope.querySelectorAll('[data-count]').forEach(node => {
        const target = parseFloat(node.dataset.count);
        const format = FORMAT[node.dataset.fmt];
        if (Number.isNaN(target) || !format) return;
        const finalText = node.textContent;
        const counter = { value: 0 };
        gsap.to(counter, { value: target, duration: 1.1, ease: 'power2.out',
          onUpdate: () => { node.textContent = format(counter.value); },
          onComplete: () => { node.textContent = finalText; } });
      });
    }, scope);
    contexts.set(scope, context);
  }

  function applyMask(root) {
    (root || document).querySelectorAll('[data-lr-client]').forEach(node => {
      if (!node.dataset.original) node.dataset.original = node.textContent;
      node.textContent = masked ? node.dataset.mask : node.dataset.original;
    });
    (root || document).querySelectorAll('[data-lr-mask]').forEach(button => {
      button.setAttribute('aria-pressed', String(masked));
      button.textContent = masked ? 'Mostrar nombres' : 'Ocultar nombres';
    });
  }

  function notify(message) {
    const inline = document.getElementById('lot-reports-error');
    if (inline) { inline.textContent = message; inline.hidden = false; }
    document.body.dispatchEvent(new CustomEvent('dn:toast', { detail: { kind: 'error', message } }));
  }

  function afterStageSwap(stage) {
    const detail = stage.querySelector('[data-lr-detail]');
    animate(stage, false);
    applyMask(stage);
    const top = Math.max(0, stage.getBoundingClientRect().top + window.scrollY - 90);
    window.scrollTo({ top, behavior: motion.matches ? 'auto' : 'smooth' });
    if (detail) {
      const heading = detail.querySelector('[data-lr-heading]');
      if (heading) heading.focus({ preventScroll: true });
    } else if (lastOpened) {
      const opener = [...stage.querySelectorAll('[data-lr-open]')].find(a => a.dataset.lrOpen === lastOpened);
      if (opener) opener.focus({ preventScroll: true });
    }
  }

  function initialize() {
    const root = document.getElementById('lot-reports');
    if (!root || root === initializedRoot) return;
    initializedRoot = root;
    const stage = document.getElementById('lot-reports-stage');
    animate(stage, true);
    applyMask(stage);
  }

  document.addEventListener('click', event => {
    const open = event.target.closest('[data-lr-open]');
    if (open) lastOpened = open.dataset.lrOpen;
    if (event.target.closest('[data-lr-mask]')) { masked = !masked; applyMask(document); }
    if (event.target.closest('[data-lr-print]')) window.print();
  });

  document.body.addEventListener('htmx:beforeRequest', event => {
    if (!event.detail.elt.closest('#lot-reports')) return;
    const error = document.getElementById('lot-reports-error');
    if (error) error.hidden = true;
    if (event.detail.target) dispose(event.detail.target);
  });
  document.body.addEventListener('htmx:afterSwap', event => {
    const target = event.detail.target;
    if (!target) return;
    initialize();
    if (target.id === 'lots-results') { animate(target, false); applyMask(target); }
    if (target.id === 'lot-reports-stage') afterStageSwap(target);
  });
  document.body.addEventListener('htmx:historyRestore', () => { initializedRoot = null; initialize(); });
  document.body.addEventListener('htmx:beforeCleanupElement', event => {
    const element = event.detail.elt;
    if (element) dispose(element);
    if (element === initializedRoot) initializedRoot = null;
  });
  document.body.addEventListener('htmx:responseError', event => {
    if (event.detail.elt.closest('#lot-reports')) notify('No fue posible actualizar el informe. Revisa tu sesión e intenta nuevamente.');
  });
  document.body.addEventListener('htmx:sendError', event => {
    if (event.detail.elt.closest('#lot-reports')) notify('Sin conexión con el servidor.');
  });
  motion.addEventListener('change', () => {
    if (motion.matches) { contexts.forEach(context => context.revert()); contexts.clear(); }
  });

  window.dnLotReports = { initialize };
  initialize();
})();
