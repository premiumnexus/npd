document.addEventListener('DOMContentLoaded',()=>{
  const source=document.querySelector('[data-packaging-unit-price]');
  const target=document.querySelector('#gate1-packaging-cost');
  const calculator=document.querySelector('#recipe-calculator');
  if(!source || !target || !calculator) return;
  const update=()=>{
    target.value=source.value || '0';
    calculator.dispatchEvent(new Event('input',{bubbles:true}));
  };
  source.addEventListener('input',update);
  source.addEventListener('change',update);
  document.addEventListener('reset',()=>setTimeout(update,0));
  update();
});
