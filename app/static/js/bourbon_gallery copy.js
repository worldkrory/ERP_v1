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
   root.querySelectorAll('[data-chapter-link]').forEach(link => {
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
     timeline.from(chapter.querySelector('.bg-chapter-number'), {
       y:24, rotationX:-35, opacity:0, duration:.5, clearProps:'transform,opacity'
     });
     timeline.from(chapter.querySelectorAll('.bg-chapter-copy > *'), {
       y:18, clipPath:'inset(0 0 100% 0)', opacity:0, duration:.5, stagger:.045,
       clearProps:'transform,opacity,clipPath'
     }, .04);
   }, chapter);
 }
 function setupMotion() {
   if (mediaContext) mediaContext.revert();
   mediaContext = null;
   if (!window.gsap || !window.ScrollTrigger) return;
   gsap.registerPlugin(ScrollTrigger);
   mediaContext = gsap.matchMedia();
   mediaContext.add('(prefers-reduced-motion: no-preference)', () => {
     const paths = root.querySelectorAll('[data-gallery-toche] path');
     paths.forEach(path => {
       const length = path.getTotalLength();
       gsap.fromTo(path, { strokeDasharray:length, strokeDashoffset:length }, {
         strokeDashoffset:0, duration:.9, delay:.1, ease:'power2.inOut',
         clearProps:'strokeDasharray,strokeDashoffset'
       });
     });
     gsap.to(root.querySelector('[data-gallery-wordmark]'), {
       xPercent:-3, ease:'none', scrollTrigger:{ trigger:root.querySelector('.bg-hero'),
         start:'top top', end:'bottom top', scrub:.8 }
     });
     gsap.from(root.querySelector('.bg-manifesto h2'), {
       y:35, clipPath:'inset(0 0 18% 0)', duration:1, ease:'power3.out',
       clearProps:'transform,clipPath', scrollTrigger:{
         trigger:root.querySelector('.bg-manifesto h2'), start:'top 85%', once:true
       }
     });
   });
   mediaContext.add('(min-width:1100px) and (min-height:700px) and (prefers-reduced-motion: no-preference)', () => {
     const stage = root.querySelector('[data-exhibition-stage]');
     const media = root.querySelector('[data-exhibition-media]');
     const copy = root.querySelector('[data-exhibition-copy]');
     stage.classList.add('is-choreographed');
     const timeline = gsap.timeline({ scrollTrigger:{ trigger:stage,
       start:'top top', end:() => '+=' + Math.round(innerHeight * 1.15),
       pin:true, scrub:.75, invalidateOnRefresh:true } });
     timeline.fromTo(media, { clipPath:'inset(0% 0% 0% 0%)' }, {
       clipPath:'inset(9% 50% 9% 5%)', duration:1, ease:'power1.inOut'
     }, 0);
     const visual = media.querySelector('img,video');
     if (visual) timeline.to(visual, { xPercent:-24, scale:.92, duration:1, ease:'power1.inOut' }, 0);
     timeline.fromTo(copy, { y:24, opacity:0 }, { y:0, opacity:1, duration:.5 }, .38);
     return () => stage.classList.remove('is-choreographed');
   });
   mediaContext.add('(max-width:1099px) and (prefers-reduced-motion: no-preference)', () => {
     const media = root.querySelector('[data-exhibition-media]');
     gsap.from(media, { clipPath:'inset(8% 8% 8% 8%)', duration:.85, ease:'power3.out',
       clearProps:'clipPath', scrollTrigger:{ trigger:media, start:'top 85%', once:true } });
   });
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
   if (event.detail.target?.id === 'bourbon-chapter') { setChapterState(); chapterMotion(); }
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
 });
 addEventListener('pagehide', () => {
   if (chapterContext) chapterContext.revert();
   if (mediaContext) { mediaContext.revert(); mediaContext = null; }
   if (video) video.pause();
 });
 addEventListener('pageshow', event => { if (event.persisted) { setupMotion(); setChapterState(); } });
 window.DNBourbonGallery = { setupMotion };
 setChapterState(); setupMotion(); setupVideo();
 document.fonts?.ready.then(() => window.ScrollTrigger?.refresh());
})();
