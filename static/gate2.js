document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('form').forEach(form=>{
    if(!form.querySelector('[value="gate2_save"]')) return;
    const mode=form.querySelector('[name="day45_target_confirmed"]');
    if(mode){
      const targets=['day45_units_store_day','day45_writeoff_percent','day45_margin_percent'].map(name=>form.querySelector(`[name="${name}"]`));
      mode.addEventListener('change',()=>targets.forEach(input=>{
        if(!input) return;
        if(mode.value==='same'){
          input.dataset.previousValue=input.value;
          input.value=input.dataset.gate0Value || '';
          input.disabled=true;
        }else{
          input.disabled=false;
          if(input.dataset.previousValue!==undefined) input.value=input.dataset.previousValue;
        }
      }));
    }
    const launch=form.querySelector('[name="launch_date"]');
    const original=form.querySelector('[name="original_launch_date"]');
    const delay=form.querySelector('[name="launch_delay_days"]');
    if(launch && original && delay){
      launch.addEventListener('change',()=>{
        const parse=value=>/^\d{4}-\d{2}-\d{2}$/.test(value)?Date.parse(value+'T00:00:00Z'):NaN;
        const first=parse(original.value),last=parse(launch.value);
        delay.value=Number.isFinite(first)&&Number.isFinite(last)?String(Math.round((last-first)/86400000)):'';
      });
    }
  });
});
