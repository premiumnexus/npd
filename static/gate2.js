document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('form').forEach(form=>{
    if(form.elements.namedItem('action')?.value!=='gate2_save') return;
    const promotion=form.elements.namedItem('marketing_has_promotion');
    if(promotion){
      const updatePromotion=()=>{
        const required=promotion.value==='yes';
        ['marketing_promotion','marketing_budget','marketing_start_date','marketing_end_date'].forEach(name=>{
          const input=form.elements.namedItem(name);
          if(!input) return;
          input.setAttribute('aria-required',String(required));
          const star=input.closest('.gate0-field')?.querySelector('[data-promotion-required]');
          if(star) star.hidden=!required;
        });
      };
      promotion.addEventListener('change',updatePromotion);
      form.addEventListener('reset',()=>setTimeout(updatePromotion,0));
      updatePromotion();
    }
    const invoice=form.elements.namedItem('vendor_invoice_price');
    if(invoice){
      const read=value=>value===undefined || value===null || String(value).trim()===''?null:Number(value);
      let recipeStatus=invoice.dataset.cogsStatus;
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
        const maximum=read(invoice.dataset.maxInvoicePrice),band=read(invoice.dataset.amberBand);
        const tolerance=Number.EPSILON*Math.max(1,Math.abs(price || 0),Math.abs(maximum || 0))*8;
        const invoiceStatus=price===null || maximum===null || maximum<=0 || band===null?'Pending':price-maximum<=tolerance?'Green':price-maximum*(1+band/100)<=tolerance?'Amber':'Red';
        const ranks={Green:0,Amber:1,Red:2};
        const overall=[recipeStatus,invoiceStatus].includes('Red')?'Red':!(recipeStatus in ranks)||!(invoiceStatus in ranks)?'Pending':ranks[recipeStatus]>=ranks[invoiceStatus]?recipeStatus:invoiceStatus;
        Object.entries({invoice_price_status:invoiceStatus,overall_cost_status:overall}).forEach(([name,status])=>{
          const input=form.elements.namedItem(name);
          if(input){input.value={Green:'Ногоон',Amber:'Шар',Red:'Улаан',Pending:'Хүлээгдэж байна'}[status];input.dataset.cogsStatus=status;}
        });
      };
      invoice.addEventListener('input',updateMargins);
      updateMargins();
      document.querySelector('#recipe-calculator')?.addEventListener('recipe-cost-change',event=>{
        invoice.dataset.finalCogs=event.detail.total===null?'':String(event.detail.total);
        recipeStatus=event.detail.status;
        updateMargins();
      });
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
