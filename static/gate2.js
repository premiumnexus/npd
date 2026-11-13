document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('form').forEach(form=>{
    if(form.elements.namedItem('action')?.value!=='gate2_save') return;
    const invoice=form.elements.namedItem('vendor_invoice_price');
    if(invoice){
      const read=value=>value===undefined || value===null || String(value).trim()===''?null:Number(value);
      const updateMargins=()=>{
        const price=invoice.validity.valid?read(invoice.value):null;
        const net=read(invoice.dataset.netPrice),rebate=read(invoice.dataset.rebate),target=read(invoice.dataset.targetMargin),cogs=read(invoice.dataset.finalCogs);
        const front=price!==null && net!==null && net>0?(1-price/net)*100:null;
        const gap=target!==null && front!==null?Math.max(0,target-front):null;
        const retained=price!==null && rebate!==null?price*(1-rebate/100):null;
        const vendor=cogs!==null && retained!==null && retained>0?(1-cogs/retained)*100:null;
        Object.entries({front_margin_percent:front,margin_gap_points:gap,implied_vendor_margin_percent:vendor}).forEach(([name,value])=>{
          const input=form.elements.namedItem(name);
          input.value=value===null?'':value.toFixed(1);
        });
      };
      invoice.addEventListener('input',updateMargins);
      updateMargins();
    }
    const mode=form.elements.namedItem('day45_target_confirmed');
    if(mode){
      const targets=['day45_units_store_day','day45_writeoff_percent','day45_margin_percent'].map(name=>form.elements.namedItem(name));
      const reason=form.elements.namedItem('day45_change_reason');
      const reasonWrapper=reason?.closest('.gate0-field');
      let previousMode=mode.value;
      const updateTargets=()=>{
        const changed=mode.value==='changed';
        if(reasonWrapper) reasonWrapper.hidden=!changed;
        if(reason) reason.disabled=!changed;
        targets.forEach(input=>{
          if(!input) return;
          if(!changed){
            if(previousMode==='changed') input.dataset.changedValue=input.value;
            input.value=input.dataset.gate0Value || '';
            input.disabled=true;
          }else{
            input.disabled=false;
            if(previousMode!=='changed' && input.dataset.changedValue!==undefined) input.value=input.dataset.changedValue;
          }
        });
        previousMode=mode.value;
      };
      mode.addEventListener('change',updateTargets);
      updateTargets();
    }
    const launch=form.elements.namedItem('launch_date');
    const original=form.elements.namedItem('original_launch_date');
    const delay=form.elements.namedItem('launch_delay_days');
    if(launch && original && delay){
      const updateLaunchDelay=()=>{
        const parse=value=>{
          if(!/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN;
          const timestamp=Date.parse(value+'T00:00:00Z');
          return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0,10)===value?timestamp:NaN;
        };
        const first=parse(original.value),last=parse(launch.value);
        delay.value=Number.isFinite(first)&&Number.isFinite(last)?String(Math.round((last-first)/86400000)):'';
      };
      launch.addEventListener('input',updateLaunchDelay);
      launch.addEventListener('change',updateLaunchDelay);
      updateLaunchDelay();
    }
  });
});
