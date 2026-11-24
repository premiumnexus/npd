document.addEventListener('DOMContentLoaded', () => {
  const section=document.querySelector('[data-gate1-production]');
  if(!section) return;
  const constraint=section.querySelector('[name="capacity_constraint"]');
  if(!constraint) return;
  const update=()=>{
    const required=constraint.value==='yes';
    section.querySelectorAll('[data-production-required]').forEach(star=>{star.hidden=!required;});
    section.querySelectorAll('[data-required-production]').forEach(input=>{input.setAttribute('aria-required',String(required));});
  };
  constraint.addEventListener('change',update);
  constraint.addEventListener('input',update);
  document.addEventListener('reset',()=>setTimeout(update,0));
  update();
});
