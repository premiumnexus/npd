document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.repeat-rows').forEach(group => {
    const button=group.querySelector('[data-add-row]');
    if (!button) return;
    button.addEventListener('click', () => {
      const total=group.querySelector('[data-row-total]');
      const index=Number(total.value);
      if (index>=100) return;
      const html=group.querySelector('[data-row-template]').innerHTML.replaceAll('__prefix__',String(index));
      group.querySelector('[data-row-list]').insertAdjacentHTML('beforeend',html);
      total.value=String(index+1);
    });
  });
  document.querySelectorAll('form').forEach(form => {
    const route=form.querySelector('[name="product_type"]');
    if (!route) return;
    const outputs={};
    form.querySelectorAll('[data-costing-output]').forEach(input=>outputs[input.dataset.costingOutput]=input);
    if(outputs.vat_percent) {
      const read=name=>{
        const input=form.querySelector(`[name="${name}"]`);
        if(!input || input.value.trim()==='' || !input.validity.valid) return null;
        const value=Number(input.value);
        return Number.isFinite(value)?value:null;
      };
      const update=()=>{
        const price=read('target_shelf_price'),margin=read('cu_margin'),rebate=read('vendor_rebate'),vendor=read('vendor_margin');
        const vat=Number(outputs.vat_percent.value);
        const net=price===null?null:price/(1+vat/100);
        const invoice=net===null || margin===null?null:net*(1-margin/100);
        const values={price_excl_vat:net,max_invoice_price:invoice,
          cogs_limit:invoice===null || rebate===null || vendor===null?null:invoice*(1-rebate/100)*(1-vendor/100),
          cu_total_margin:margin===null || rebate===null?null:(1-(1-margin/100)*(1-rebate/100))*100};
        Object.entries(values).forEach(([key,value])=>{outputs[key].value=value===null?'':value.toFixed(key==='cu_total_margin'?1:0);});
      };
      ['target_shelf_price','cu_margin','vendor_rebate','vendor_margin'].forEach(name=>form.querySelector(`[name="${name}"]`).addEventListener('input',update));
      update();
    }
    const toggle=()=>{
      ['existing_sku','improvement_reasons','improvement_reason'].forEach(name=>{
        const input=form.querySelector(`[name="${name}"]`);
        const wrapper=input && input.closest('.gate0-field');
        if(wrapper) wrapper.hidden=route.value!=='improvement';
      });
    };
    route.addEventListener('change',toggle); toggle();
    const category=form.querySelector('[name="category"]');
    const subcategory=form.querySelector('[name="subcategory"]');
    if(category && subcategory && !subcategory.disabled) {
      const options=JSON.parse(subcategory.dataset.options || '[]');
      category.addEventListener('change',()=>{
        subcategory.replaceChildren(new Option('---------',''));
        options.filter(option=>option.category===category.value).forEach(option=>subcategory.add(new Option(option.label,option.code)));
      });
    }
  });
});
