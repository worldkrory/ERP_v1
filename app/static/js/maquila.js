(() => {
 if(window.dnMaquila) return; window.dnMaquila=true;
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');
 function animate(root){if(window.gsap&&!reduce.matches)gsap.from(root.querySelectorAll('.dn-ui-panel,.mq-forecast'),{y:12,opacity:0,duration:.35,stagger:.05,clearProps:'transform,opacity'});}
 document.addEventListener('click',e=>{
  if(e.target.closest('#mq-add')){let rows=document.querySelectorAll('.mq-line');if(rows.length>=20)return;let row=rows[0].cloneNode(true);row.querySelectorAll('input,select').forEach(x=>x.value='');document.querySelector('#mq-lines').append(row);}
  const b=e.target.closest('[data-remove]');if(b&&document.querySelectorAll('.mq-line').length>1)b.closest('.mq-line').remove();
 });
 document.addEventListener('htmx:afterSwap',e=>{if(e.detail.target.id==='mq-forecast')animate(e.detail.target);});
 document.addEventListener('htmx:sendError',()=>{let n=document.querySelector('#mq-error');if(n){n.hidden=false;n.textContent='Sin conexión. No se registró una entrega desde el pronóstico.';}});
 document.querySelector('#mq-form')?.addEventListener('submit',e=>{const b=e.target.querySelector('button[type=submit]');if(b)b.disabled=true;});
 animate(document);
})();

(() => {
  if (window.dnMaquilaLotFilter) return;
  window.dnMaquilaLotFilter = true;

  function updateLots() {
    const origin = document.querySelector(
      '#mq-form [name="origin_id"]'
    );
    if (!origin) return;

    document.querySelectorAll(
      '#mq-lines select[name="batch_id"]'
    ).forEach(select => {
      const previous = select.value;

      [...select.options].forEach(option => {
        if (!option.value) {
          option.textContent = origin.value
            ? 'Selecciona un lote disponible'
            : 'Selecciona primero una bodega';
          return;
        }

        const availableHere =
          option.dataset.location === origin.value;

        option.hidden = !availableHere;
        option.disabled = !availableHere;
      });

      const stillAvailable = [...select.options].some(
        option =>
          option.value === previous &&
          !option.disabled
      );

      if (!stillAvailable) select.value = '';
    });
  }

  document.addEventListener('change', event => {
    if (event.target.matches(
      '#mq-form [name="origin_id"]'
    )) {
      updateLots();
    }
  });

  const lines = document.getElementById('mq-lines');

  if (lines) {
    new MutationObserver(updateLots).observe(
      lines,
      { childList: true }
    );
  }

  updateLots();
})();