(() => {
  'use strict';
  if (window.DNBourbonMobile) return;
  const root = document.querySelector('.dn-bourbon-gallery');
  if (!root) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const compact = matchMedia('(max-width: 1099px)');
  const section = root.querySelector('[data-reveal]');
  const stage = section && section.querySelector('[data-reveal-stage]');
  const range = section && section.querySelector('[data-reveal-range]');
  const openButton = section && section.querySelector('[data-reveal-open]');
  const status = section && section.querySelector('[data-reveal-status]');
  const heroLink = root.querySelector('.bg-hero .bg-pill');
  const state = {
    p:0, target:0, open:false, armed:false, dragging:false,
    pointerId:null, startX:0, startP:0,
    timeline:null, setter:null, nudge:null, context:null, collabContext:null
  };

  const clamp = value => Math.min(1, Math.max(0, value));

  function setOpen(open) {
    if (!section || state.open === open) return;
    state.open = open;
    section.classList.toggle('is-open', open);
    if (stage) stage.dataset.state = open ? 'open' : 'closed';
    if (status) status.textContent = open ? 'La niebla se abrió. Sigue bajando para continuar la historia.' : '';
    if (openButton) openButton.textContent = open ? 'Cerrar la niebla' : 'Descubrir';
  }
  function setTarget(value) {
    if (!state.armed || !state.setter) return;
    const next = clamp(value);
    state.target = next;
    if (range) range.value = String(Math.round(next * 100));
    state.setter(next);
    setOpen(next >= .98);
  }
  function snap() { setTarget(state.target >= .5 ? 1 : 0); }
  function stopNudge() { if (state.nudge) { state.nudge.kill(); state.nudge = null; } }

  function disarm() {
    stopNudge();
    if (state.context) { state.context.revert(); state.context = null; }
    if (state.collabContext) { state.collabContext.revert(); state.collabContext = null; }
    state.timeline = null; state.setter = null; state.armed = false;
    state.p = 0; state.target = 0; state.open = false; state.dragging = false;
    if (section) section.classList.remove('is-armed', 'is-open');
    if (stage) stage.dataset.state = 'closed';
    if (range) range.value = '0';
    if (openButton) openButton.textContent = 'Descubrir';
    if (status) status.textContent = '';
  }

  function arm() {
    disarm();
    if (heroLink) heroLink.setAttribute('href', compact.matches && section ? '#niebla' : '#pieza');
    if (!section || !stage || !compact.matches || reduced.matches || !window.gsap) return;
    const image = section.querySelector('[data-reveal-image]');
    const left = section.querySelector('[data-reveal-mist-left]');
    const right = section.querySelector('[data-reveal-mist-right]');
    const toche = section.querySelector('[data-reveal-toche]');
    const paths = [...section.querySelectorAll('[data-reveal-toche] path')];
    const hint = section.querySelector('[data-reveal-hint]');
    const arrow = section.querySelector('[data-reveal-arrow]');
    const line = section.querySelector('[data-reveal-line]');
    if (!left || !right || !toche || !line) return;
    section.classList.add('is-armed');
    state.armed = true;
    state.context = gsap.context(() => {
      const lengths = paths.map(path => path.getTotalLength());
      paths.forEach((path, index) => { path.style.strokeDasharray = String(lengths[index]); });
      const timeline = gsap.timeline({ paused:true, defaults:{ ease:'none' } });
      paths.forEach((path, index) => {
        timeline.fromTo(path, { strokeDashoffset:lengths[index] * .72 }, { strokeDashoffset:0, duration:.55, ease:'power1.out' }, 0);
      });
      timeline.fromTo(left, { xPercent:0 }, { xPercent:-112, duration:.8, ease:'power2.inOut' }, .2);
      timeline.fromTo(right, { xPercent:0 }, { xPercent:112, duration:.8, ease:'power2.inOut' }, .2);
      if (image) timeline.fromTo(image, { scale:1.14, opacity:.55 }, { scale:1, opacity:1, duration:.8, ease:'power2.out' }, .2);
      timeline.fromTo(toche, { opacity:1, yPercent:0, scale:1 }, { opacity:0, yPercent:-16, scale:.7, duration:.35, ease:'power2.in' }, .62);
      if (hint) timeline.fromTo(hint, { opacity:1 }, { opacity:0, duration:.08 }, 0);
      timeline.fromTo(line, { opacity:0, y:14 }, { opacity:1, y:0, duration:.25, ease:'power2.out' }, .75);
      state.timeline = timeline;
      timeline.progress(0);
      state.setter = gsap.quickTo(state, 'p', { duration:.3, ease:'power3.out', onUpdate:() => timeline.progress(state.p) });
      if (arrow) state.nudge = gsap.to(arrow, { x:10, duration:.8, repeat:-1, yoyo:true, ease:'sine.inOut' });
    }, section);

    const collab = root.querySelector('.bg-collab');
    if (collab && window.ScrollTrigger) {
      gsap.registerPlugin(ScrollTrigger);
      state.collabContext = gsap.context(() => {
        const names = collab.querySelectorAll('.bg-collab-name');
        const cross = collab.querySelector('.bg-collab-x');
        const timeline = gsap.timeline({
          defaults:{ ease:'power3.out' },
          scrollTrigger:{ trigger:collab, start:'top 78%', once:true }
        });
        if (names[0]) timeline.from(names[0], { xPercent:-14, opacity:0, duration:.7, clearProps:'transform,opacity' }, 0);
        if (cross) timeline.from(cross, { rotation:-90, scale:.4, opacity:0, duration:.7, ease:'back.out(1.8)', clearProps:'transform,opacity' }, .12);
        if (names[1]) timeline.from(names[1], { xPercent:14, opacity:0, duration:.7, clearProps:'transform,opacity' }, .2);
        timeline.from(collab.querySelector('.bg-collab-line'), { y:14, opacity:0, duration:.5, clearProps:'transform,opacity' }, .5);
      }, collab);
    }
  }

  if (stage) {
    stage.addEventListener('pointerdown', event => {
      if (!state.armed || (event.pointerType === 'mouse' && event.button !== 0)) return;
      state.dragging = true;
      state.pointerId = event.pointerId;
      state.startX = event.clientX;
      state.startP = state.target;
      stopNudge();
      try { stage.setPointerCapture(event.pointerId); } catch (_) {}
    });
    stage.addEventListener('pointermove', event => {
      if (!state.dragging || event.pointerId !== state.pointerId) return;
      setTarget(state.startP + (event.clientX - state.startX) / (stage.clientWidth * .72));
    });
    const end = event => {
      if (!state.dragging || event.pointerId !== state.pointerId) return;
      state.dragging = false;
      try { stage.releasePointerCapture(event.pointerId); } catch (_) {}
      snap();
    };
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', end);
  }
  if (range) {
    range.addEventListener('input', () => { stopNudge(); setTarget(Number(range.value) / 100); });
    range.addEventListener('change', snap);
  }
  if (openButton) openButton.addEventListener('click', () => { stopNudge(); setTarget(state.open ? 0 : 1); });

  document.addEventListener('error', event => {
    if (event.target instanceof HTMLImageElement && event.target.hasAttribute('data-reveal-image')) {
      event.target.hidden = true;
      const fallback = root.querySelector('[data-reveal-fallback]');
      if (fallback) fallback.hidden = false;
    }
  }, true);

  // Folio por gesto: el cambio sigue pasando por los enlaces HTMX existentes.
  const links = () => [...root.querySelectorAll('[data-chapter-link]')];
  const activeIndex = () => Math.max(0, links().findIndex(link => link.classList.contains('is-active')));
  document.addEventListener('click', event => {
    const link = event.target.closest('[data-chapter-link]');
    if (!link) return;
    window.DNBourbonDirection = links().indexOf(link) >= activeIndex() ? 1 : -1;
  }, true);
  const layout = root.querySelector('.bg-notebook-layout');
  if (layout) {
    let tracking = false, startX = 0, startY = 0, pointerId = null;
    layout.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' || !compact.matches || event.target.closest('a,button,input,select,textarea')) return;
      tracking = true; pointerId = event.pointerId; startX = event.clientX; startY = event.clientY;
    });
    layout.addEventListener('pointerup', event => {
      if (!tracking || event.pointerId !== pointerId) return;
      tracking = false;
      const dx = event.clientX - startX, dy = event.clientY - startY;
      if (Math.abs(dx) < 64 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
      const list = links();
      const next = list[activeIndex() + (dx < 0 ? 1 : -1)];
      if (next) next.click();
    });
    layout.addEventListener('pointercancel', () => { tracking = false; });
  }

  root.querySelectorAll('[data-share]').forEach(button => {
    button.addEventListener('click', async () => {
      const output = root.querySelector('[data-share-status]');
      const url = document.querySelector('link[rel="canonical"]')?.href || (location.origin + location.pathname);
      const data = { title:'Bourbon Rosado · Densa Niebla', text:'Descubre el origen de este microlote de Guavatá, Santander.', url };
      try {
        if (navigator.share) { await navigator.share(data); if (output) output.textContent = ''; }
        else if (navigator.clipboard) { await navigator.clipboard.writeText(url); if (output) output.textContent = 'Enlace copiado.'; }
        else if (output) output.textContent = 'Copia el enlace desde la barra del navegador.';
      } catch (error) {
        if (error && error.name !== 'AbortError' && output) output.textContent = 'No se pudo compartir. Copia el enlace desde la barra del navegador.';
      }
    });
  });

  compact.addEventListener('change', arm);
  reduced.addEventListener('change', arm);
  addEventListener('pagehide', disarm);
  addEventListener('pageshow', event => { if (event.persisted) arm(); });
  window.DNBourbonMobile = { arm, disarm };
  arm();
})();
