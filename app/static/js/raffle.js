(() => {
  'use strict';
  if (window.DNRaffle) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const ZONE_ID = 'raffle-form-zone';
  let context = null;
  let pageMatch = null;

  function revert() { if (context) { context.revert(); context = null; } }

  function splitCode(node) {
    if (node.dataset.split) return [...node.querySelectorAll('.raffle-code-char')];
    const text = node.dataset.code || node.textContent.trim();
    node.textContent = '';
    const readable = document.createElement('span');
    readable.className = 'raffle-sr-only';
    readable.textContent = text;
    const visual = document.createElement('span');
    visual.setAttribute('aria-hidden', 'true');
    const chars = [...text].map(character => {
      const span = document.createElement('span');
      span.className = 'raffle-code-char';
      span.textContent = character;
      visual.appendChild(span);
      return span;
    });
    node.append(readable, visual);
    node.dataset.split = '1';
    return chars;
  }

  function animateSuccess(card) {
    revert();
    if (!window.gsap || reduced.matches) return;
    context = gsap.context(() => {
      const mark = card.querySelector('.success-mark');
      const code = card.querySelector('[data-raffle-code]');
      const chars = code ? splitCode(code) : [];
      const rest = [...card.children].filter(child => child !== mark);
      const timeline = gsap.timeline({ defaults:{ ease:'power3.out' } });
      timeline.from(card, { y:18, opacity:0, duration:.45, clearProps:'transform,opacity' }, 0);
      if (mark) {
        timeline.from(mark, { scale:.3, rotation:-120, opacity:0, duration:.75, ease:'back.out(1.8)', clearProps:'transform,opacity' }, .05);
        timeline.fromTo(mark, { boxShadow:'0 0 0 0 rgba(215,187,124,.55)' }, { boxShadow:'0 0 0 22px rgba(215,187,124,0)', duration:.95, ease:'power2.out', clearProps:'boxShadow' }, .4);
      }
      timeline.from(rest, { y:14, opacity:0, duration:.45, stagger:.07, clearProps:'transform,opacity' }, .2);
      if (chars.length) {
        timeline.from(chars, { y:16, rotationX:-70, opacity:0, duration:.5, stagger:.045, ease:'back.out(1.6)', clearProps:'transform,opacity' }, .55);
      }
    }, card);
  }

  function reactToError(zone) {
    const invalid = zone.querySelector('[aria-invalid="true"]');
    if (!invalid) return;
    invalid.focus({ preventScroll:false });
    if (window.gsap && !reduced.matches) {
      const group = invalid.closest('.field-group, .check-row') || invalid;
      gsap.fromTo(group, { x:-7 }, { x:0, duration:.55, ease:'elastic.out(1,.35)', clearProps:'transform' });
    }
  }

  function initPage() {
    if (!window.gsap) return;
    pageMatch = gsap.matchMedia();
    pageMatch.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.prize-card', { y:26, opacity:0, duration:.65, stagger:.1, ease:'power3.out', clearProps:'transform,opacity' });
      gsap.to('.raffle-orbit-one', { x:34, y:-22, duration:14, yoyo:true, repeat:-1, ease:'sine.inOut' });
      gsap.to('.raffle-orbit-two', { x:-28, y:18, duration:11, yoyo:true, repeat:-1, ease:'sine.inOut' });
    });
  }

  document.addEventListener('htmx:beforeSwap', event => {
    const target = event.detail.target;
    if (!target || target.id !== ZONE_ID) return;
    if ([409, 410, 429, 500, 503].includes(event.detail.xhr.status)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  document.addEventListener('htmx:afterSwap', event => {
    const target = event.detail.target;
    if (!target || target.id !== ZONE_ID) return;
    const success = target.querySelector('[data-raffle-success]');
    if (success) animateSuccess(success);
    else reactToError(target);
  });

  function networkProblem(event) {
    const zone = document.getElementById(ZONE_ID);
    if (!zone || !zone.contains(event.detail.elt || zone)) return;
    const node = zone.querySelector('[data-raffle-network-error]');
    if (node) node.hidden = false;
  }
  document.addEventListener('htmx:sendError', networkProblem);
  document.addEventListener('htmx:responseError', networkProblem);
  document.addEventListener('htmx:beforeRequest', () => {
    const node = document.querySelector('[data-raffle-network-error]');
    if (node) node.hidden = true;
  });

  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-copy-code]');
    if (!button) return;
    const card = button.closest('[data-raffle-success]');
    const code = card && card.querySelector('[data-raffle-code]');
    const status = card && card.querySelector('[data-copy-status]');
    const text = code && (code.dataset.code || code.textContent.trim());
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      if (status) status.textContent = 'Código copiado.';
    } catch (_) {
      if (status) status.textContent = 'No se pudo copiar. Selecciónalo y cópialo manualmente.';
    }
  });

  window.addEventListener('pagehide', () => { revert(); if (pageMatch) { pageMatch.revert(); pageMatch = null; } });
  window.DNRaffle = { animateSuccess };
  initPage();
})();
