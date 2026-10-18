(() => {
 'use strict';
 if (window.DNBourbonGallery) return;
 const root = document.querySelector('.dn-bourbon-gallery');
 if (!root) return;
 const reduced = matchMedia('(prefers-reduced-motion: reduce)');
 let mediaContext = null;
 let chapterContext = null;
 let observer = null;
 const video = root.querySelector('[data-gallery-video]');
 const playButton = root.querySelector('[data-video-toggle]');
 const soundButton = root.querySelector('[data-sound-toggle]');
 const errorNode = root.querySelector('[data-chapter-error]');
 let manuallyPaused = false;

 function setChapterState() {
   const chapter = document.getElementById('bourbon-chapter');
   if (!chapter) return;
   const links = [...root.querySelectorAll('[data-chapter-link]')];
   const index = Math.max(0, links.findIndex(link => link.dataset.chapterLink === chapter.dataset.chapterKey));
   const meter = root.querySelector('[data-chapter-meter]');
   if (meter) {
     const value = (index + 1) / Math.max(1, links.length);
     if (window.gsap && !reduced.matches) gsap.to(meter, { scaleX:value, duration:.35, ease:'power2.out', overwrite:true });
     else meter.style.transform = `scaleX(${value})`;
   }
   links.forEach(link => {
     const active = link.dataset.chapterLink === chapter.dataset.chapterKey;
     link.classList.toggle('is-active', active);
     if (active) link.setAttribute('aria-current','true');
     else link.removeAttribute('aria-current');
   });
 }
 function chapterMotion() {
   if (chapterContext) chapterContext.revert();
   chapterContext = null;
   const chapter = document.getElementById('bourbon-chapter');
   if (!chapter || reduced.matches || !window.gsap) return;
   chapterContext = gsap.context(() => {
     const timeline = gsap.timeline({ defaults:{ ease:'power3.out' } });
     timeline.from(chapter.querySelector('.bg-chapter-inner'), {
       x:16 * (window.DNBourbonDirection || 1), rotationY:-4 * (window.DNBourbonDirection || 1), transformOrigin:'left center', duration:.55,
       clearProps:'transform,transformOrigin'
     }, 0);
     timeline.from(chapter.querySelector('.bg-chapter-number'), {
       y:20, opacity:0, duration:.42, clearProps:'transform,opacity'
     }, .02);
     timeline.from(chapter.querySelectorAll('.bg-chapter-copy > *'), {
       y:14, opacity:0, duration:.42, stagger:.045,
       clearProps:'transform,opacity'
     }, .08);
   }, chapter);
 }
 let journeyLength = 0;
 let journeyProgress = 0;
 let journeyPoints = [];
 function paintJourney(progress) {
   journeyProgress = progress;
   const path = root.querySelector('[data-route-progress]');
   if (path) path.style.strokeDashoffset = String(journeyLength * (1 - progress));
   const height = root.querySelector('#contenido').getBoundingClientRect().height;
   root.querySelectorAll('[data-route-node]').forEach((node,index) => {
     node.classList.toggle('is-passed', journeyPoints[index] && journeyPoints[index].y <= progress * height + 80);
   });
 }
 function layoutJourney() {
   const main = root.querySelector('#contenido');
   const svg = root.querySelector('[data-story-route]');
   if (!main || !svg) return;
   const bounds = main.getBoundingClientRect();
   const height = Math.max(1200, Math.round(bounds.height));
   const steps = [...root.querySelectorAll('[data-journey-step]')].filter(step => step.getBoundingClientRect().height > 0);
   journeyPoints = steps.map((step,index) => {
     const box = step.getBoundingClientRect();
     return { x:index % 2 ? 24 : 52,
       y:Math.max(28, Math.min(height - 40, box.top - bounds.top + Math.min(160, box.height * .2))) };
   });
   const points = [{x:40,y:12}, ...journeyPoints, {x:40,y:height - 12}];
   let d = `M${points[0].x} ${points[0].y}`;
   for (let index=1; index<points.length; index++) {
     const a = points[index - 1], b = points[index];
     const mid = (a.y + b.y) / 2;
     d += ` C${a.x} ${mid} ${b.x} ${mid} ${b.x} ${b.y}`;
   }
   svg.setAttribute('viewBox', `0 0 80 ${height}`);
   svg.querySelector('[data-route-track]').setAttribute('d',d);
   const path = svg.querySelector('[data-route-progress]');
   path.setAttribute('d',d);
   journeyLength = path.getTotalLength();
   path.style.strokeDasharray = String(journeyLength);
   const nodes = svg.querySelector('[data-route-nodes]');
   nodes.replaceChildren();
   journeyPoints.forEach(point => {
     const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
     circle.setAttribute('cx',point.x); circle.setAttribute('cy',point.y);
     circle.setAttribute('r','4'); circle.setAttribute('class','bg-route-node');
     circle.setAttribute('data-route-node',''); nodes.appendChild(circle);
   });
   paintJourney(reduced.matches || !window.ScrollTrigger ? 1 : journeyProgress);
 }
 function setupMotion() {
   if (mediaContext) mediaContext.revert();
   mediaContext = null;
   layoutJourney();
   if (!window.gsap || !window.ScrollTrigger) { paintJourney(1); return; }
   gsap.registerPlugin(ScrollTrigger);
   mediaContext = gsap.matchMedia();
   mediaContext.add('(min-width:1100px) and (min-height:700px) and (prefers-reduced-motion: no-preference)', () => {
     const stage = root.querySelector('[data-exhibition-stage]');
     const media = root.querySelector('[data-exhibition-media]');
     const copy = root.querySelector('[data-exhibition-copy]');
     stage.classList.add('is-choreographed');
     const timeline = gsap.timeline({ scrollTrigger:{ trigger:stage,
       start:'top top', end:() => '+=' + Math.round(innerHeight * .9),
       pin:true, scrub:.8, invalidateOnRefresh:true } });
     timeline.fromTo(media, { clipPath:'inset(0% 0% 0% 0%)' }, {
       clipPath:'inset(9% 50% 9% 5%)', duration:1, ease:'power1.inOut'
     }, 0);
     const visual = media.querySelector('img,video');
     if (visual) timeline.to(visual, { xPercent:-24, scale:.92, duration:1, ease:'power1.inOut' }, 0);
     timeline.fromTo(copy, { y:28, opacity:0 }, { y:0, opacity:1, duration:.5 }, .3);
     return () => stage.classList.remove('is-choreographed');
   });
   mediaContext.add('(prefers-reduced-motion: no-preference)', () => {
     root.querySelectorAll('[data-gallery-toche] path').forEach(path => {
       const length = path.getTotalLength();
       gsap.fromTo(path, { strokeDasharray:length, strokeDashoffset:length }, {
         strokeDashoffset:0, duration:.9, delay:.1, ease:'power2.inOut',
         clearProps:'strokeDasharray,strokeDashoffset'
       });
     });
     ScrollTrigger.create({ trigger:root.querySelector('#contenido'),
       start:'top top', end:'bottom bottom',
       onUpdate:self => paintJourney(self.progress),
       onRefresh:self => { layoutJourney(); paintJourney(self.progress); }
     });
     const mists = root.querySelectorAll('[data-notebook-mist]');
     mists.forEach((mist,index) => {
       gsap.fromTo(mist, { xPercent:index ? 7 : -8, yPercent:6 }, {
         xPercent:index ? -7 : 8, yPercent:-6, ease:'none',
         scrollTrigger:{ trigger:root.querySelector('#cuaderno'), start:'top bottom', end:'bottom top', scrub:1.1 }
       });
     });
     gsap.from(root.querySelector('.bg-manifesto h2'), {
       y:26, duration:.85, ease:'power3.out', clearProps:'transform',
       scrollTrigger:{ trigger:root.querySelector('.bg-manifesto h2'), start:'top 85%', once:true }
     });
     gsap.from(root.querySelector('.bg-invitation h2'), {
       y:24, duration:.8, ease:'power3.out', clearProps:'transform',
       scrollTrigger:{ trigger:root.querySelector('.bg-invitation h2'), start:'top 90%', once:true }
     });
   });
   mediaContext.add('(max-width:1099px) and (prefers-reduced-motion: no-preference)', () => {
     const media = root.querySelector('[data-exhibition-media]');
     gsap.from(media, { clipPath:'inset(5% 5% 5% 5%)', duration:.75, ease:'power3.out',
       clearProps:'clipPath', scrollTrigger:{ trigger:media, start:'top 85%', once:true } });
   });
   mediaContext.add('(prefers-reduced-motion: reduce)', () => { layoutJourney(); paintJourney(1); });
   ScrollTrigger.refresh();
 }
 function updateVideoButtons() {
   if (!video) return;
   if (playButton) {
     playButton.textContent = video.paused ? 'Reproducir película' : 'Pausar película';
     playButton.setAttribute('aria-pressed', String(!video.paused));
   }
   if (soundButton) {
     soundButton.textContent = video.muted ? 'Activar sonido' : 'Silenciar';
     soundButton.setAttribute('aria-pressed', String(!video.muted));
   }
 }
 function loadVideo() {
   if (video && !video.getAttribute('src')) {
     video.src = video.dataset.videoSrc;
     video.load();
   }
 }
 function setupVideo() {
   if (!video) return;
   video.addEventListener('play', updateVideoButtons);
   video.addEventListener('pause', updateVideoButtons);
   video.addEventListener('volumechange', updateVideoButtons);
   video.addEventListener('loadedmetadata', () => window.ScrollTrigger?.refresh());
   video.addEventListener('error', () => {
     const fallback = root.querySelector('[data-media-fallback]');
     if (fallback) fallback.hidden = false;
     if (playButton) playButton.disabled = true;
     if (soundButton) soundButton.disabled = true;
   });
   playButton?.addEventListener('click', async () => {
     if (video.paused) {
       loadVideo(); manuallyPaused = false;
       try { await video.play(); } catch (_) { manuallyPaused = true; }
     } else { manuallyPaused = true; video.pause(); }
     updateVideoButtons();
   });
   soundButton?.addEventListener('click', async () => {
     loadVideo(); video.muted = !video.muted;
     try { await video.play(); manuallyPaused = false; }
     catch (_) { video.muted = true; }
     updateVideoButtons();
   });
   if ('IntersectionObserver' in window) {
     observer = new IntersectionObserver(async entries => {
       const visible = entries[0].isIntersecting;
       if (!visible) { video.pause(); return; }
       if (reduced.matches || navigator.connection?.saveData || manuallyPaused) return;
       loadVideo();
       try { await video.play(); } catch (_) {}
     }, { threshold:.35 });
     observer.observe(video);
   }
 }
 document.addEventListener('error', event => {
   if (event.target instanceof HTMLImageElement && event.target.hasAttribute('data-gallery-image')) {
     event.target.hidden = true;
     root.querySelector('[data-media-fallback]')?.removeAttribute('hidden');
   }
 }, true);
 document.addEventListener('htmx:beforeRequest', event => {
   if (event.detail.target?.id === 'bourbon-chapter' && errorNode) {
     errorNode.hidden = true;
   }
 });
 document.addEventListener('htmx:beforeSwap', event => {
   if (event.detail.target?.id !== 'bourbon-chapter') return;
   if (event.detail.xhr.status >= 200 && event.detail.xhr.status < 300) {
     const parsed = new DOMParser().parseFromString(event.detail.xhr.responseText, 'text/html');
     if (!parsed.getElementById('bourbon-chapter') || parsed.querySelector('main')) {
       event.detail.shouldSwap = false;
       if (errorNode) { errorNode.textContent = 'No se pudo abrir el capítulo. Usa el enlace para recargar la página.'; errorNode.hidden = false; }
     } else if (chapterContext) { chapterContext.revert(); chapterContext = null; }
   }
 });
 document.addEventListener('htmx:afterSwap', event => {
   if (event.detail.target?.id === 'bourbon-chapter') {
     setChapterState(); chapterMotion();
     requestAnimationFrame(() => { layoutJourney(); window.ScrollTrigger?.refresh(); });
   }
 });
 function chapterError(event) {
   if (event.detail.target?.id !== 'bourbon-chapter' || !errorNode) return;
   errorNode.textContent = 'No se pudo abrir el capítulo. La información anterior se conserva. Recarga la página si continúa.';
   errorNode.hidden = false;
 }
 document.addEventListener('htmx:responseError', chapterError);
 document.addEventListener('htmx:sendError', chapterError);
 document.addEventListener('htmx:historyRestore', () => {
   if (document.querySelector('.dn-bourbon-gallery') === root) { setChapterState(); window.ScrollTrigger?.refresh(); }
   else location.reload();
 });
 document.addEventListener('visibilitychange', () => { if (document.hidden && video) video.pause(); });
 reduced.addEventListener('change', () => {
   if (chapterContext) { chapterContext.revert(); chapterContext = null; }
   if (reduced.matches && video) video.pause();
   requestAnimationFrame(layoutJourney);
 });
 addEventListener('pagehide', () => {
   if (chapterContext) chapterContext.revert();
   if (mediaContext) { mediaContext.revert(); mediaContext = null; }
   if (video) video.pause();
 });
 addEventListener('pageshow', event => { if (event.persisted) { setupMotion(); setChapterState(); } });
 window.DNBourbonGallery = { setupMotion };
 setChapterState(); setupMotion(); setupVideo();
 document.fonts?.ready.then(() => { layoutJourney(); window.ScrollTrigger?.refresh(); });
 root.querySelectorAll('[data-gallery-image]').forEach(image => image.addEventListener('load', () => { layoutJourney(); window.ScrollTrigger?.refresh(); }, { once:true }));
 let routeResizeTimer;
 addEventListener('resize', () => { clearTimeout(routeResizeTimer); routeResizeTimer = setTimeout(() => { layoutJourney(); window.ScrollTrigger?.refresh(); }, 140); });
})();
