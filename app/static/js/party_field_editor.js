(() => {
  'use strict';
  if (window.dnPartyFieldEditor) return;

  function message(text, error = false) {
    const node = document.getElementById('party-editor-feedback');
    if (!node) return;
    node.textContent = text;
    node.dataset.tone = error ? 'error' : 'info';
    node.hidden = !text;
  }
  function enhanceLists(root) {
    root.querySelectorAll('[data-party-list-source]').forEach(source => {
      if (source.dataset.ready) return;
      let values;
      try { values = JSON.parse(source.value); } catch (_) { return; }
      if (!Array.isArray(values)) return;
      source.dataset.ready = '1';
      source.hidden = true;
      const wrapper = document.createElement('div');
      const chips = document.createElement('div');
      chips.className = 'dn-ui-tag-list';
      const controls = document.createElement('div');
      controls.className = 'dn-ui-actions';
      const input = document.createElement('input');
      input.className = 'dn-ui-input';
      input.type = 'text'; input.maxLength = 200;
      input.placeholder = 'Código de responsabilidad';
      input.dataset.partyListNew = 'true';
      input.setAttribute('aria-label', 'Nueva responsabilidad fiscal');
      const add = document.createElement('button');
      add.type = 'button'; add.className = 'dn-ui-button'; add.textContent = 'Añadir';
      const hint = document.createElement('small');
      hint.className = 'dn-ui-muted';
      hint.textContent = 'Los códigos nuevos se guardan como texto. Los elementos existentes se conservan sin reinterpretarlos.';
      function render() {
        chips.replaceChildren();
        values.forEach((value,index) => {
          const chip = document.createElement('span'); chip.className = 'dn-ui-tag';
          const label = document.createElement('span');
          label.textContent = typeof value === 'string' ? value : (typeof value === 'object' && value !== null ? 'Elemento estructurado' : `${value} (${typeof value})`);
          const remove = document.createElement('button');
          remove.type = 'button'; remove.className = 'dn-ui-tag-remove'; remove.textContent = 'Quitar';
          remove.setAttribute('aria-label', `Quitar elemento ${index + 1}`);
          remove.addEventListener('click', () => { values.splice(index,1); sync(); });
          chip.append(label,remove); chips.append(chip);
        });
      }
      function sync() {
        source.value = JSON.stringify(values);
        source.dispatchEvent(new Event('input',{ bubbles:true }));
        render();
      }
      function append() {
        const value = input.value.trim();
        if (!value) return;
        if (values.length >= 100) { message('Se permiten hasta 100 responsabilidades.',true); return; }
        if (!values.includes(value)) { values.push(value); sync(); }
        input.value = ''; input.focus();
      }
      add.addEventListener('click',append);
      input.addEventListener('keydown',event => { if (event.key === 'Enter') { event.preventDefault(); append(); } });
      controls.append(input,add); wrapper.append(chips,controls,hint);
      source.after(wrapper); render();
    });
  }
  document.addEventListener('submit', event => {
    if (!event.target.matches('[data-party-edit-form]')) return;
    const pending = [...event.target.querySelectorAll('[data-party-list-new]')].find(input => input.value.trim());
    if (pending) {
      event.preventDefault(); event.stopImmediatePropagation();
      message('Pulsa Añadir para incorporar el código pendiente antes de guardar.',true); pending.focus();
    }
  }, true);
  document.addEventListener('input', event => {
    const form = event.target.closest('[data-party-edit-form]');
    if (form) form.dataset.dirty = '1';
  });
  document.addEventListener('change', event => {
    const form = event.target.closest('[data-party-edit-form]');
    if (form) form.dataset.dirty = '1';
  });
  document.addEventListener('click', event => {
    const link = event.target.closest('[data-party-section-link]');
    if (!link) return;
    const section = document.querySelector(link.getAttribute('href'));
    if (section) section.open = true;
  });
  document.addEventListener('htmx:beforeRequest', event => {
    const target = event.detail.target;
    if (!target?.hasAttribute('data-party-field')) return;
    const source = event.detail.elt;
    const open = document.querySelector('#party-editor [data-party-edit-form]');
    if (open && !target.contains(open)) {
      event.preventDefault(); message('Guarda o cancela el editor abierto antes de editar otro dato.'); return;
    }
    if (open && source.matches('[data-discard-edit]') && open.dataset.dirty === '1'
        && !window.confirm('¿Descartar los cambios sin guardar de este editor?')) {
      event.preventDefault(); return;
    }
    message('');
  });
  document.addEventListener('htmx:beforeSend', event => {
    const form = event.detail.elt;
    if (form?.matches('[data-party-edit-form]')) {
      const controls = form.querySelector('[data-party-edit-controls]');
      if (controls) controls.disabled = true;
      form.setAttribute('aria-busy','true');
    }
  });
  document.addEventListener('htmx:beforeSwap', event => {
    const target = event.detail.target;
    if (!target?.hasAttribute('data-party-field')) return;
    const parsed = new DOMParser().parseFromString(event.detail.xhr.responseText,'text/html');
    const replacement = parsed.getElementById(target.id);
    if (!replacement || parsed.querySelector('[data-admin-app]')) {
      event.detail.shouldSwap = false;
      message('No se recibió el editor esperado. Revisa tu sesión y recarga la ficha.',true);
      return;
    }
    if ([200,409,422,503].includes(event.detail.xhr.status)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
      window.DNAdminUI?.cleanup(target);
    }
  });
  document.addEventListener('htmx:afterSwap', event => {
    const id = event.detail.target?.id;
    if (!id?.startsWith('party-field-')) return;
    const target = document.getElementById(id);
    if (!target) return;
    enhanceLists(target);
    const error = target.querySelector('[role="alert"]');
    const form = target.querySelector('[data-party-edit-form]');
    if (error) error.focus();
    else if (form) {
      const first = [...form.querySelectorAll('input:not([type="hidden"]),select,textarea')].find(node => !node.hidden && !node.disabled);
      first?.focus({ preventScroll:true });
    }
    if (target.hasAttribute('data-party-saved')) window.DNAdminUI?.highlight(target);
    else if (!error) window.DNAdminUI?.reveal(target,'[data-party-edit-body]');
  });
  document.addEventListener('htmx:afterRequest', event => {
    const form = event.detail.elt;
    if (form?.matches('[data-party-edit-form]')) {
      form.removeAttribute('aria-busy');
      const controls = form.querySelector('[data-party-edit-controls]');
      if (controls) controls.disabled = false;
    }
  });
  document.addEventListener('htmx:sendError', event => {
    if (event.detail.target?.hasAttribute('data-party-field')) message('No se pudo confirmar la respuesta. Recarga los valores actuales antes de volver a guardar.',true);
  });
  const root = document.getElementById('party-editor');
  if (root) enhanceLists(root);
  window.dnPartyFieldEditor = { enhanceLists };
})();
