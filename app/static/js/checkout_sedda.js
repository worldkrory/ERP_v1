(() => {
'use strict';
function init(){
 const form=document.getElementById('checkout-form');if(!form||form.dataset.seddaInit)return;form.dataset.seddaInit='1';
 const city=document.getElementById('ciudad_codigo'),label=document.getElementById('ciudad_q'),target=document.getElementById('quote-panel');
 const fog=document.getElementById('quote-fog'),btn=document.getElementById('confirm-btn');
 const status=document.getElementById('shipping-request-status'),retry=document.getElementById('shipping-retry');
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');
 let valid=false,expiry=null;
 // Button stays disabled: this package does not pretend to implement payment/order creation.
 btn.disabled=true;
 const paths=[...document.querySelectorAll('.toche-progress path')];
 const lengths=paths.map(p=>p.getTotalLength());
 function progress(){
  const fields=[...form.querySelectorAll('[required]')];
  const done=fields.filter(x=>x.checkValidity()).length;
  const ratio=((city.value?1:0)+(fields.length?done/fields.length:0)+(valid?1:0))/3;
  paths.forEach((p,i)=>{p.style.strokeDasharray=lengths[i];const offset=lengths[i]*(1-Math.max(0,Math.min(1,ratio*paths.length-i)));
   if(window.gsap&&!reduce.matches)gsap.to(p,{strokeDashoffset:offset,duration:.35,overwrite:true});else p.style.strokeDashoffset=offset;});
 }
 function invalidate(message){valid=false;clearTimeout(expiry);btn.disabled=true;retry.hidden=!city.value;if(status)status.textContent=message||'';progress();}
 function selectedDestination(){return city.value.length===5?city.value+'000':city.value;}
 document.addEventListener('htmx:configRequest',event=>{
  if(event.detail.target?.id==='quote-panel'){
   event.detail.headers['X-Shipping-CSRF']=document.getElementById('shipping-csrf').value;
  }
 });
 document.addEventListener('htmx:beforeRequest',event=>{
  if(event.detail.target?.id!=='quote-panel')return;
  invalidate('Consultando el envío…');
 });
 document.addEventListener('htmx:beforeSwap',event=>{
  if(event.detail.target?.id!=='quote-panel')return;
  // El código de destino viaja con la petición; descartar respuestas antiguas.
  const params=event.detail.requestConfig?.parameters;
  const requested=params?.ciudad_codigo;
  if(requested&&String(requested)!==city.value){event.detail.shouldSwap=false;return;}
 });
 document.addEventListener('htmx:afterSwap',event=>{
  if(event.detail.target?.id!=='quote-panel')return;
  if(fog)fog.style.display='none';
  const result=target.querySelector('[data-shipping-valid]');
  if(!result||result.dataset.shippingValid!=='true'){invalidate('Revisa el mensaje de envío.');return;}
  if(result.dataset.shippingDestination!==selectedDestination()){invalidate('Cambió el destino. Cotiza nuevamente.');return;}
  const ms=Number(result.dataset.shippingExpires)*1000-Date.now();
  if(!(ms>0)){invalidate('Cotización vencida. Vuelve a cotizar.');return;}
  valid=true;retry.hidden=true;status.textContent='Envío cotizado desde Manizales.';
  clearTimeout(expiry);expiry=setTimeout(()=>invalidate('La cotización venció. Vuelve a cotizar.'),ms);
  if(fog)fog.style.display='none';
  if(window.gsap&&!reduce.matches)gsap.from(target.children,{opacity:0,y:12,duration:.4,stagger:.07,clearProps:'transform,opacity'});
  progress();document.dispatchEvent(new CustomEvent('checkout:shipping-ready',{detail:{destination:city.value}}));
 });
 document.getElementById('city-results').addEventListener('click',event=>{
  const option=event.target.closest('.city-option');if(!option)return;
  // No cambiar ni aceptar código de destino desde texto libre.
  const values=JSON.parse(option.getAttribute('hx-vals'));
  city.value=values.ciudad_codigo;label.value=option.dataset.label;
  document.querySelectorAll('#city-results .city-option').forEach(o=>{o.setAttribute('hx-sync','#quote-panel:replace');});
  setTimeout(()=>document.getElementById('city-results').replaceChildren(),100);
  progress();
 },true);
 label.addEventListener('input',()=>{city.value='';if(window.htmx)htmx.trigger(target,'htmx:abort');target.textContent='Selecciona tu ciudad para cotizar.';invalidate('Selecciona una ciudad del listado.');});
 retry.addEventListener('click',()=>{if(city.value&&window.htmx)htmx.ajax('POST',form.dataset.quoteUrl||'/checkout/cotizar',{
   target:'#quote-panel',swap:'innerHTML',values:{ciudad_codigo:city.value},headers:{'X-Shipping-CSRF':document.getElementById('shipping-csrf').value}});});
 form.addEventListener('input',progress);form.addEventListener('submit',e=>e.preventDefault());
 document.querySelectorAll('.fog-step').forEach(s=>{s.removeAttribute('inert');s.classList.add('is-open');s.style.visibility='visible';s.style.opacity='1';});
 ['htmx:sendError','htmx:responseError'].forEach(name=>document.addEventListener(name,e=>{if(e.detail.target?.id==='quote-panel')invalidate('No pudimos consultar el envío. Reintenta o recarga el checkout.');}));
 if(fog)fog.style.pointerEvents='none';progress();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();