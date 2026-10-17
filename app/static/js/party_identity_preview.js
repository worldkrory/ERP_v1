(() => {
  'use strict';
  if (window.DNPartyIdentityPreview) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let state = null;
  let timer;

  function dispose() {
    clearTimeout(timer);
    if (state?.context) state.context.revert();
    if (state) state.context = null;
  }
  function synchronize(animate = false) {
    if (!state) return;
    const natural = state.type.value === 'NATURAL';
    const first = state.first.value.trim();
    const last = state.last.value.trim();
    const signature = JSON.stringify([natural, first, last]);
    const changed = signature !== state.signature;

    state.root.hidden = !natural;
    state.legalField.hidden = natural;
    state.root.dataset.empty = first || last ? 'false' : 'true';
    state.firstText.textContent = first;
    state.lastText.textContent = last;
    state.lastText.hidden = !last;
    state.placeholder.hidden = Boolean(first || last);
    state.caption.textContent = first
      ? 'Así aparecerá el nombre completo. Vista previa, aún sin guardar.'
      : 'Escribe los nombres. El apellido se puede completar después.';

    state.signature = signature;
    if (!changed) return;
    dispose();
    if (!animate || !natural || !first || reduced.matches) return;
    const thisState = state;
    timer = setTimeout(() => {
      if (state !== thisState || !state.root.isConnected
          || state.signature !== signature || reduced.matches || !window.gsap) return;
      if (state.root.getBoundingClientRect().height === 0) return;
      const library = window.gsap;
      const context = library.context(() => {
        const timeline = library.timeline({ defaults:{ ease:'power2.out' } });
        timeline.fromTo(
          state.avatar.querySelector('svg'),
          {
            scale: .92,
            rotation: -3
          },
          {
            scale: 1,
            rotation: 0,
            duration: .3,
            clearProps: 'transform'
          }
        );
        timeline.fromTo(state.lastText.hidden ? state.firstText : state.lastText,
          { y:5, opacity:.65 },
          { y:0, opacity:1, duration:.28, clearProps:'transform,opacity' }, 0
        );
        timeline.fromTo(state.rule,
          { scaleX:.15 },
          { scaleX:1, duration:.42, clearProps:'transform' }, .03
        );
      }, state.root);
      state.context = context;
    }, 320);
  }
  function initialize() {
    const root = document.getElementById('customer-identity-preview');
    if (!root) { dispose(); state = null; return; }
    if (state?.root === root) return;
    dispose();
    const form = document.getElementById('customer-form');
    const legal = document.getElementById('legal_name');
    const legalField = legal?.closest('[data-customer-legal-field]');
    const type = document.getElementById('party_type');
    const first = document.getElementById('first_name');
    const last = document.getElementById('last_name');
    if (!form || !legalField || !type || !first || !last) {
      state = null;
      return;
    }
    state = { root, form, legalField, type, first, last, signature:null, context:null,
      firstText:root.querySelector('[data-identity-first]'),
      lastText:root.querySelector('[data-identity-last]'),
      placeholder:root.querySelector('[data-identity-placeholder]'),
      avatar: root.querySelector('[data-identity-avatar]'),
      caption:root.querySelector('[data-identity-caption]'),
      rule:root.querySelector('[data-identity-rule]')
    };
    synchronize(false);
    if (!reduced.matches) window.DNAdminUI?.gsapReady();
  }
  document.addEventListener('input', event => {
    if (!state || !state.form.contains(event.target)) return;
    if (['first_name','last_name'].includes(event.target.id)) synchronize(!event.isComposing);
  });
  document.addEventListener('compositionend', event => {
    if (['first_name','last_name'].includes(event.target.id)) synchronize(true);
  });
  document.addEventListener('change', event => {
    if (event.target.id === 'party_type') synchronize(false);
  });
  document.addEventListener('reset', event => {
    if (event.target.id === 'customer-form') setTimeout(() => synchronize(false), 0);
  });
  document.addEventListener('htmx:afterSwap', initialize);
  document.addEventListener('htmx:beforeCleanupElement', event => {
    const element = event.detail.elt;
    if (state && element && (element === state.root || element.contains(state.root))) {
      dispose(); state = null;
    }
  });
  reduced.addEventListener('change', () => dispose());
  addEventListener('pagehide', dispose);
  addEventListener('pageshow', () => { initialize(); synchronize(false); });
  window.DNPartyIdentityPreview = { initialize };
  initialize();
})();
