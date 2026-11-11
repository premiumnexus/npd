document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('form').forEach(form=>{
    if(!form.querySelector('[value="gate2_save"]')) return;
    const invoice=form.querySelector('[name="vendor_invoice_price"]');
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
          const input=form.querySelector(`[name="${name}"]`);
          input.value=value===null?'':value.toFixed(1);
        });
      };
      invoice.addEventListener('input',updateMargins);
      updateMargins();
    }
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
