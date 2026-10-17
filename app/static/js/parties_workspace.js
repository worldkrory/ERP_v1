(() => {
  'use strict';
  if (window.dnPartiesWorkspace) return;
  let root;
  let form;
  let saving = false;
  let createdId = null;
  let opener = null;

  function showMessage(message, tone = 'info') {
    const node = document.getElementById('customer-feedback');
    if (!node) return;
    node.textContent = message;
    node.dataset.tone = tone;
    node.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    node.hidden = !message;
  }
  function syncDocument() {
    const documentType = document.getElementById('document_type');
    const dv = document.getElementById('verification_digit');
    if (!documentType || !dv) return;
    const nit = documentType.value === 'NIT';
    dv.required = nit;
    dv.disabled = !nit;
    syncPersonNames();
  }
  function syncPersonNames() {
    const type = document.getElementById('party_type');
    const first = document.getElementById('first_name');
    const last = document.getElementById('last_name');
    const legal = document.getElementById('legal_name');

    if (!type || !first || !last || !legal) return;

    const natural = type.value === 'NATURAL';

    document
      .querySelectorAll('[data-customer-person-name]')
      .forEach(node => {
        node.hidden = !natural;
      });

    first.required = natural;
    last.required = false;

    first.disabled = !natural;
    last.disabled = !natural;

    legal.readOnly = natural;

    if (natural) {
      legal.value = [
        first.value.trim(),
        last.value.trim()
      ].filter(Boolean).join(' ');
    }
  }
  document.addEventListener('input', event => {
  if (
    event.target.id === 'first_name'
    || event.target.id === 'last_name'
  ) {
    syncPersonNames();
  }
  });

  document.addEventListener('change', event => {
    if (event.target.id === 'party_type') {
      syncPersonNames();
    }
  });
  function initialize() {
    const nextRoot = document.getElementById('parties-workspace');
    if (!nextRoot || nextRoot === root) return;
    root = nextRoot;
    form = document.getElementById('customer-form');
    const fields = form && form.querySelector('[data-customer-fields]');
    if (fields) fields.disabled = false;
    syncDocument();
    if (window.DNAdminUI && !matchMedia('(prefers-reduced-motion: reduce)').matches) window.DNAdminUI.gsapReady();
  }
  document.addEventListener('click', event => {
    const open = event.target.closest('[data-customer-open]');
    if (open) {
      const panel = document.getElementById('customer-create-panel');
      if (!panel) return;
      event.preventDefault();
      opener = open;
      panel.open = true;
      panel.scrollIntoView({ block:'start', behavior:'auto' });
      requestAnimationFrame(() => document.getElementById('party_type')?.focus({ preventScroll:true }));
    }
    if (event.target.closest('[data-customer-clear]')) {
      const filters = document.getElementById('customer-filters');
      if (filters) { filters.elements.q.value = ''; filters.elements.profile.value = ''; }
    }
  });
  document.addEventListener('change', event => {
    if (event.target.id === 'document_type') syncDocument();
  });
  document.addEventListener('reset', event => {
    if (event.target.id === 'customer-form') setTimeout(syncDocument, 0);
  });
  document.addEventListener('toggle', event => {
    const panel = event.target;
    if (!(panel instanceof HTMLElement) || panel.id !== 'customer-create-panel') return;
    if (panel.open) window.DNAdminUI?.reveal(panel.querySelector('[data-customer-form-body]'));
    else window.DNAdminUI?.cleanup(panel);
  }, true);

  document.addEventListener('submit', async event => {
    if (event.target.id !== 'customer-form') return;
    event.preventDefault();
    const currentForm = event.target;
    if (saving || !currentForm.reportValidity()) return;
    const value = name => currentForm.elements.namedItem(name).value.trim();
    const payload = {
      first_name: value('party_type') === 'NATURAL'
        ? value('first_name')
        : null,

      last_name: value('party_type') === 'NATURAL'
        ? value('last_name')
        : null,
      party_type:value('party_type'), document_type:value('document_type'),
      document_number:value('document_number'), legal_name:value('legal_name'),
      verification_digit:value('document_type') === 'NIT' ? value('verification_digit') || null : null,
      trade_name:value('trade_name'), email:value('email'), phone:value('phone'),
      whatsapp:value('whatsapp'), payment_term_days:value('payment_term_days'),
      roles:[...currentForm.querySelectorAll('input[name="roles"]:checked')].map(input => input.value)
    };
    if (!payload.document_number || !payload.legal_name) {
      showMessage('Documento y nombre son obligatorios.', 'error'); return;
    }
    const button = document.getElementById('save-customer');
    const fields = currentForm.querySelector('[data-customer-fields]');
    saving = true;
    fields.disabled = true;
    button.textContent = 'Guardando…';
    currentForm.setAttribute('aria-busy', 'true');
    showMessage('');
    let confirmed = false;
    try {
      const headers = { 'Content-Type':'application/json', 'Accept':'application/json' };
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
      if (csrf) headers['X-CSRFToken'] = csrf;
      const response = await fetch(root.dataset.createUrl, {
        method:'POST', credentials:'same-origin', headers, body:JSON.stringify(payload)
      });
      if (!response.headers.get('Content-Type')?.includes('application/json')) {
        throw new Error('Respuesta inesperada. Revisa tu sesión y busca el documento antes de repetir el registro.');
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No fue posible guardar el cliente.');
      confirmed = true;
      currentForm.reset();
      showMessage(`Cliente ${data.display_name || payload.legal_name} guardado. El directorio se filtrará por su documento.`, 'success');
      createdId = Number(data.id);
      const filters = document.getElementById('customer-filters');
      filters.elements.q.value = payload.document_number;
      filters.elements.profile.value = '';
      if (window.htmx) window.htmx.trigger(filters, 'submit');
      else showMessage('Cliente guardado. Recarga el directorio para consultarlo.', 'success');
    } catch (error) {
      showMessage(error instanceof TypeError
        ? 'No se pudo confirmar la respuesta. Busca el documento antes de intentar guardar nuevamente.'
        : error.message, confirmed ? 'info' : 'error');
    } finally {
      saving = false;
      fields.disabled = false;
      syncDocument();
      button.textContent = 'Guardar cliente';
      currentForm.removeAttribute('aria-busy');
    }
  });

  document.addEventListener('htmx:beforeRequest', event => {
    if (event.detail.target?.id === 'customer-directory') {
      document.getElementById('customer-directory')?.setAttribute('aria-busy', 'true');
    }
  });
  document.addEventListener('htmx:beforeSwap', event => {
    if (event.detail.target?.id !== 'customer-directory') return;
    if (event.detail.xhr.status >= 200 && event.detail.xhr.status < 300) {
      const html = new DOMParser().parseFromString(event.detail.xhr.responseText, 'text/html');
      if (!html.getElementById('customer-directory') || html.querySelector('[data-admin-app]')) {
        event.detail.shouldSwap = false;
        showMessage('La sesión o la respuesta cambió. Recarga la página antes de continuar.', 'error');
      } else window.DNAdminUI?.cleanup(event.detail.target);
    }
  });
  document.addEventListener('htmx:afterSwap', event => {
    initialize();
    if (event.detail.target?.id !== 'customer-directory') return;
    const directory = document.getElementById('customer-directory');
    if (!directory) return;
    directory.removeAttribute('aria-busy');
    window.DNAdminUI?.reveal(directory, '[data-customer-row]');
    if (createdId) {
      const row = directory.querySelector(`[data-customer-id="${createdId}"]`);
      if (row) window.DNAdminUI?.highlight(row);
      createdId = null;
    }
  });
  document.addEventListener('htmx:afterRequest', event => {
    if (event.detail.target?.id === 'customer-directory') document.getElementById('customer-directory')?.removeAttribute('aria-busy');
  });
  function directoryError(event) {
    if (event.detail.target?.id !== 'customer-directory') return;
    showMessage(createdId
      ? 'El cliente fue guardado, pero el directorio no pudo actualizarse. No vuelvas a registrarlo; recarga la búsqueda.'
      : 'No fue posible actualizar el directorio. Se conservan los resultados anteriores.', 'error');
    createdId = null;
    document.getElementById('customer-directory')?.removeAttribute('aria-busy');
  }
  document.addEventListener('htmx:responseError', directoryError);
  document.addEventListener('htmx:sendError', directoryError);
  window.dnPartiesWorkspace = { initialize };
  initialize();
})();
