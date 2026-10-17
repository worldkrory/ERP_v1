(() => {
  'use strict';
  if (window.DNAdminUI) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const contexts = new Map();
  let libraryPromise;

  function gsapReady() {
    if (window.gsap) return Promise.resolve(window.gsap);
    if (libraryPromise) return libraryPromise;
    libraryPromise = new Promise(resolve => {
      let settled = false;
      let timer;
      const finish = () => {
        if (settled) return;
        settled = true;
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
      if (root === element || element.contains(root)) { context.revert(); contexts.delete(root); }
    });
  }
  async function reveal(root, selector) {
    if (!root || reduced.matches) return;
    cleanup(root);
    const started = performance.now();
    const library = await gsapReady();
    if (!library || !root.isConnected || reduced.matches || performance.now() - started > 650) return;
    const nodes = selector ? [...root.querySelectorAll(selector)].filter(node => {
      const box = node.getBoundingClientRect();
      return box.top < innerHeight && box.bottom > 0;
    }).slice(0, 12) : [root];
    if (!nodes.length) return;
    const context = library.context(() => {
      library.from(nodes, { y:8, opacity:0, duration:.24, stagger:.02,
        ease:'power2.out', clearProps:'transform,opacity' });
    }, root);
    contexts.set(root, context);
  }
  async function highlight(root) {
    if (!root || reduced.matches) return;
    cleanup(root);
    const library = await gsapReady();
    if (!library || !root.isConnected || reduced.matches) return;
    const context = library.context(() => {
      library.fromTo(root, { backgroundColor:'#e3f1e8' }, {
        backgroundColor:'transparent', duration:1.1, ease:'power2.out', clearProps:'backgroundColor'
      });
    }, root);
    contexts.set(root, context);
  }
  document.addEventListener('htmx:beforeCleanupElement', event => {
    if (event.detail.elt) cleanup(event.detail.elt);
  });
  reduced.addEventListener('change', () => { if (reduced.matches) cleanup(document.documentElement); });
  addEventListener('pagehide', () => cleanup(document.documentElement));
  async function expandDetails(details) {
  cleanup(details);

  if (!details.open || reduced.matches) return;

  const summary = details.querySelector(':scope > summary');
  const body = details.querySelector(
    ':scope > .dn-ui-panel-body'
  );

  if (!summary || !body) return;

  const started = performance.now();
  const library = await gsapReady();

  if (
    !library
    || !details.isConnected
    || !details.open
    || reduced.matches
    || performance.now() - started > 650
  ) {
    return;
  }

  const closedHeight =
    summary.getBoundingClientRect().height + 2;

  const expandedHeight =
    details.getBoundingClientRect().height;

  const children = [...body.children].slice(0, 12);

  const context = library.context(() => {
    const timeline = library.timeline({
      defaults: { ease: 'power2.out' }
    });

    timeline.fromTo(
      details,
      {
        height: closedHeight,
        overflow: 'hidden'
      },
      {
        height: expandedHeight,
        duration: 0.34,
        clearProps: 'height,overflow'
      }
    );

    if (children.length) {
      timeline.from(
        children,
        {
          y: 10,
          opacity: 0,
          duration: 0.25,
          stagger: 0.025,
          clearProps: 'transform,opacity'
        },
        0.06
      );
    }
  }, details);

  contexts.set(details, context);
}
  window.DNAdminUI = { reveal, highlight, cleanup, gsapReady, expandDetails };
})();
