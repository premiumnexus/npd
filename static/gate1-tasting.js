document.addEventListener('DOMContentLoaded', () => {
  const section=document.querySelector('[data-gate1-tasting]');
  if(!section) return;
  const count=section.querySelector('[name="consumer_test"]');
  if(!count) return;
  const update=()=>{
    const required=count.value.trim()!=='';
    section.querySelectorAll('[data-consumer-required]').forEach(star=>{star.hidden=!required;});
    section.querySelectorAll('[data-required-consumer]').forEach(input=>{input.setAttribute('aria-required',String(required));});
  };
  count.addEventListener('input',update);
  count.addEventListener('change',update);
  document.addEventListener('reset',()=>setTimeout(update,0));
  update();
});
