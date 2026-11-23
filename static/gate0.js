document.addEventListener('DOMContentLoaded', () => {
  const updateEvidenceReminders = root => {
    root.querySelectorAll('[data-evidence-level]').forEach(select => {
      const reminder=select.closest('.repeat-row').querySelector('[data-evidence-reminder]');
      if(reminder) reminder.hidden=Boolean(select.value);
    });
  };
  updateEvidenceReminders(document);
  document.addEventListener('change',event=>{
    if(event.target.matches('[data-evidence-level]')) updateEvidenceReminders(event.target.closest('.repeat-row'));
  });
  document.addEventListener('reset',event=>setTimeout(()=>updateEvidenceReminders(event.target),0));
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
      updateEvidenceReminders(group);
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
        const writeoff=read('day45_writeoff_percent');
        values.day45_margin_percent=values.cu_total_margin===null || writeoff===null?null:values.cu_total_margin-writeoff;
        Object.entries(values).forEach(([key,value])=>{if(outputs[key]) outputs[key].value=value===null?'':value.toFixed(key==='day45_margin_percent'?2:key==='cu_total_margin'?1:0);});
      };
      ['target_shelf_price','cu_margin','vendor_rebate','vendor_margin','day45_writeoff_percent'].forEach(name=>form.querySelector(`[name="${name}"]`).addEventListener('input',update));
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
      category.addEventListener('change',()=>{
        const placeholder=new Option(subcategory.getAttribute('placeholder') || '---------','',true,true);
        if(subcategory.hasAttribute('data-gate-placeholder')) {
          placeholder.disabled=true;
          placeholder.hidden=true;
        }
        subcategory.replaceChildren(placeholder);
        // Read the current dataset, which also includes options added in this page.
        const currentOptions=JSON.parse(subcategory.dataset.options || '[]');
        currentOptions.filter(option=>option.category===category.value && !Array.from(subcategory.options).some(item=>item.value===option.code)).forEach(option=>subcategory.add(new Option(option.label,option.code)));
        if(subcategory.hasAttribute('data-options-url')) subcategory.add(new Option('+ Нэмэх','__add_option__'));
        subcategory.dataset.optionScope=category.value;
        subcategory.dataset.previousOption='';
      });
    }
  });
});
