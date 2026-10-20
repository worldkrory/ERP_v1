(() => {
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const canAnimate = () => window.gsap && !motion.matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const fmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 4 });
  const form = () => document.getElementById('transfer-form');

  function updateRoute() {
    const f = form();
    if (!f) return;
    const from = f.elements.from_location_id;
    const to = f.elements.to_location_id;
    if (to.value && to.value === from.value) to.value = '';
    $$('option', to).forEach(o => { o.disabled = !!o.value && o.value === from.value; });
    $$('option', from).forEach(o => { o.disabled = !!o.value && o.value === to.value; });

    [['origin', from], ['dest', to]].forEach(([key, select]) => {
      const node = $(`[data-node="${key}"]`);
      if (!node) return;
      const option = select.selectedOptions[0];
      const text = option && option.value ? option.dataset.name : '—';
      const label = $('strong', node);
      if (label.textContent !== text) {
        label.textContent = text;
        node.classList.toggle('is-set', !!select.value);
        if (canAnimate()) gsap.fromTo(node, { y: -6 }, { y: 0, duration: .35, ease: 'back.out(2)' });
      }
    });
    updateSummary();
  }

  function updateSummary() {
    const f = form();
    if (!f) return;
    const lines = $$('[data-line] input[type=number]', f).filter(i => parseFloat(i.value) > 0);
    const units = lines.reduce((sum, i) => sum + parseFloat(i.value), 0);
    $('#transfer-summary-text').textContent = lines.length
      ? `${lines.length} línea${lines.length > 1 ? 's' : ''} · ${fmt.format(units)} unidades`
      : 'Sin productos seleccionados';
    const from = f.elements.from_location_id.value;
    const to = f.elements.to_location_id.value;
    $('#transfer-submit').disabled = !(lines.length && from && to && from !== to);
  }

  function refreshLine(input) {
    input.closest('[data-line]').classList.toggle('is-active', parseFloat(input.value) > 0);
    updateSummary();
  }

  function setQty(input, value) {
    const max = parseFloat(input.max);
    const v = Math.min(Math.max(value, 0), Number.isFinite(max) ? max : value);
    input.value = v > 0 ? String(v) : '';
    refreshLine(input);
  }

  function toast(kind, message) {
    let stack = $('#dn-toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'dn-toast-stack';
      stack.setAttribute('role', 'status');
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    const el = document.createElement('p');
    el.className = `dn-toast dn-toast-${kind}`;
    el.textContent = message;
    stack.appendChild(el);
    const remove = () => el.remove();
    if (canAnimate()) {
      gsap.fromTo(el, { x: 40, opacity: 0 }, { x: 0, opacity: 1, duration: .35, ease: 'power3.out' });
      gsap.to(el, { opacity: 0, y: -8, duration: .3, delay: 5, onComplete: remove });
    } else setTimeout(remove, 5500);
  }

  function travel() {
    const box = $('#transfer-route');
    const dot = $('.dn-route-dot');
    if (!box || !dot || !canAnimate()) return;
    const center = n => n.offsetLeft + n.offsetWidth / 2;
    const origin = $('[data-node="origin"]', box);
    const transit = $('[data-node="transit"]', box);
    gsap.timeline()
      .set(dot, { left: center(origin), opacity: 1 })
      .to(dot, { left: center(transit), duration: .9, ease: 'power2.inOut' })
      .fromTo(transit, { scale: 1 }, { scale: 1.07, duration: .18, yoyo: true, repeat: 1 }, '-=.05')
      .to(dot, { opacity: 0, duration: .4, delay: .4 });
  }

  document.addEventListener('click', e => {
    const step = e.target.closest('[data-step]');
    if (step) {
      const input = $('input', step.closest('[data-line]'));
      setQty(input, (parseFloat(input.value) || 0) + Number(step.dataset.step));
      return;
    }
    const all = e.target.closest('[data-all]');
    if (all) setQty($('input', all.closest('[data-line]')), parseFloat($('input', all.closest('[data-line]')).max));
  });

  document.addEventListener('input', e => {
    if (e.target.matches('[data-line] input[type=number]')) refreshLine(e.target);
    if (e.target.id === 'transfer-search') {
      const q = e.target.value.trim().toLowerCase();
      $$('[data-line]').forEach(l => { l.hidden = !!q && !l.dataset.name.includes(q); });
    }
  });

  document.addEventListener('change', e => {
    if (e.target.matches('[data-line] input[type=number]')) setQty(e.target, parseFloat(e.target.value) || 0);
    if (e.target.matches('#transfer-form select')) updateRoute();
  });

  document.body.addEventListener('htmx:afterSwap', e => {
    const target = e.detail.target;
    if (target.id === 'transfer-stock') {
      updateSummary();
      if (canAnimate()) gsap.from($$('[data-line]', target), {
        y: 14, opacity: 0, duration: .4, stagger: .035, ease: 'power2.out', clearProps: 'transform,opacity',
      });
    }
    if (target.id === 'transfer-board') {
      const card = $('[data-flash]', target);
      if (card && canAnimate()) gsap.fromTo(card,
        { backgroundColor: 'rgba(184,146,74,.30)', y: -10 },
        { backgroundColor: 'rgba(184,146,74,0)', y: 0, duration: 1.4, ease: 'power2.out',
          clearProps: 'backgroundColor,transform' });
    }
  });

  document.body.addEventListener('dn:toast', e => toast(e.detail.kind, e.detail.message));

  document.body.addEventListener('dn:dispatched', () => {
    const f = form();
    if (!f) return;
    $$('[data-line] input[type=number]', f).forEach(i => { i.value = ''; });
    ['tracking_number', 'freight_cost', 'notes'].forEach(n => { f.elements[n].value = ''; });
    travel();
    if (window.htmx) htmx.trigger(f.elements.from_location_id, 'change');
    updateSummary();
  });

  document.addEventListener('DOMContentLoaded', () => {
    updateRoute();
    if (canAnimate()) gsap.from('.dn-transfer-composer', {
      y: 20, opacity: 0, duration: .5, ease: 'power3.out', clearProps: 'transform,opacity',
    });
  });
})();