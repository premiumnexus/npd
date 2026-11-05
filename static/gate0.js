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
