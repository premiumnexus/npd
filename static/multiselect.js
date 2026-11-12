document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('select[multiple][data-multiselect]').forEach(select => {
    const dropdown = document.createElement('details');
    dropdown.className = 'gate-multiselect';
    const summary = document.createElement('summary');
    summary.setAttribute('aria-labelledby', select.labels[0]?.id || `${select.id}_label`);
    if (select.labels[0] && !select.labels[0].id) select.labels[0].id = `${select.id}_label`;
    const choices = document.createElement('div');
    choices.className = 'gate-multiselect-choices';
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'link';
    add.textContent = '+ Нэмэх';
    dropdown.append(summary, choices, add);
    select.after(dropdown);
    select.hidden = true;
    let signature = '';
    const update = () => {
      const options = Array.from(select.options).filter(option => option.value && option.value !== '__add_option__');
      const next = JSON.stringify(options.map(option => [option.value, option.textContent]));
      if (next !== signature) {
        choices.replaceChildren();
        options.forEach(option => {
          const label = document.createElement('label');
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = option.value;
          checkbox.addEventListener('change', () => {
            option.selected = checkbox.checked;
            select.dispatchEvent(new Event('change', {bubbles: true}));
          });
          label.append(checkbox, document.createTextNode(option.textContent));
          choices.append(label);
        });
        signature = next;
      }
      choices.querySelectorAll('input').forEach(checkbox => {
        const option = options.find(item => item.value === checkbox.value);
        checkbox.checked = option.selected;
        checkbox.disabled = select.disabled || option.disabled;
      });
      const selected = options.filter(option => option.selected).map(option => option.textContent);
      summary.textContent = selected.join(', ') || 'Сонгоно уу';
      summary.classList.toggle('placeholder', selected.length === 0);
      summary.setAttribute('aria-disabled', String(select.disabled));
      add.hidden = select.disabled;
    };
    add.addEventListener('click', () => {
      const action = Array.from(select.options).find(option => option.value === '__add_option__');
      if (action) {
        action.selected = true;
        select.dispatchEvent(new Event('change', {bubbles: true}));
      }
    });
    summary.addEventListener('click', event => { if (select.disabled) event.preventDefault(); });
    select.addEventListener('change', update);
    select.form?.addEventListener('reset', () => setTimeout(update, 0));
    document.addEventListener('click', event => { if (!dropdown.contains(event.target)) dropdown.open = false; });
    dropdown.addEventListener('keydown', event => {
      if (event.key === 'Escape') { dropdown.open = false; summary.focus(); }
    });
    update();
  });
});
