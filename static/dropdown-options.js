document.addEventListener('DOMContentLoaded', () => {
  const addValue = '__add_option__';
  const dialog = document.createElement('dialog');
  dialog.className = 'dropdown-option-dialog';
  dialog.innerHTML = '<form><h2>Шинэ сонголт нэмэх</h2><label for="new-dropdown-option">Нэр</label><input id="new-dropdown-option" name="label" required maxlength="200" autocomplete="off"><p role="alert" data-option-error></p><div class="dropdown-option-actions"><button type="button" class="secondary" data-option-cancel>Болих</button><button type="submit" class="button">Хадгалах</button></div></form>';
  document.body.append(dialog);
  const editor = dialog.querySelector('form');
  const input = editor.elements.label;
  const error = dialog.querySelector('[data-option-error]');
  const save = editor.querySelector('[type="submit"]');
  const ingredientFields = document.createElement('div');
  ingredientFields.hidden = true;
  ingredientFields.innerHTML = '<label for="new-option-supplier">Нийлүүлэгчийн нэр</label><input id="new-option-supplier" name="supplier" required maxlength="160" disabled><label for="new-option-price">Үнэ (₮ / кг)</label><input id="new-option-price" name="price" type="number" min="0" step="0.01" required disabled>';
  input.after(ingredientFields);
  let active = null;
  let saving = false;
  const remember = select => {
    if (select.multiple) {
      const values = Array.from(select.selectedOptions, option => option.value);
      if (!values.includes(addValue)) select.dataset.previousOptions = JSON.stringify(values);
      return;
    }
    if (select.value !== addValue) select.dataset.previousOption = select.value;
  };
  document.querySelectorAll('select[data-options-url]').forEach(remember);
  document.addEventListener('focusin', event => {
    if (event.target.matches('select[data-options-url]')) remember(event.target);
  });
  document.addEventListener('change', event => {
    const select = event.target;
    if (!select.matches('select[data-options-url]')) return;
    const adding = select.multiple ? Array.from(select.selectedOptions).some(option => option.value === addValue) : select.value === addValue;
    if (!adding) { remember(select); return; }
    event.stopImmediatePropagation();
    if (select.multiple) {
      const previous = JSON.parse(select.dataset.previousOptions || '[]');
      Array.from(select.options).forEach(option => { option.selected = previous.includes(option.value); });
    } else {
      select.value = select.dataset.previousOption || '';
    }
    active = select;
    input.value = '';
    const isIngredient = select.dataset.optionField === 'recipe_ingredient';
    input.maxLength = select.dataset.optionField === 'category' ? 80 : isIngredient ? 160 : 200;
    ingredientFields.hidden = !isIngredient;
    ingredientFields.querySelectorAll('input').forEach(field => { field.disabled = !isIngredient; field.value = ''; });
    error.textContent = '';
    dialog.showModal();
    input.focus();
  }, true);
  dialog.querySelector('[data-option-cancel]').addEventListener('click', () => {
    if (!saving) dialog.close();
  });
  dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
  editor.addEventListener('submit', async event => {
    event.preventDefault();
    if (!active || saving) return;
    const label = input.value.trim();
    if (!label) { input.focus(); return; }
    const select = active;
    const scope = select.dataset.optionScope || '';
    const token = (select.form || select.closest('form')).querySelector('[name="csrfmiddlewaretoken"]').value;
    saving = true;
    save.disabled = true;
    error.textContent = '';
    try {
      const response = await fetch(select.dataset.optionsUrl, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': token},
        body: JSON.stringify({stage: select.dataset.optionStage, field: select.dataset.optionField,
          scope, label, supplier: editor.elements.supplier.value, price: editor.elements.price.value,
          food: select.dataset.optionFood || select.closest('.gate0-fields[data-option-food]')?.dataset.optionFood || ''})
      });
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Хадгалж чадсангүй. Дахин нэвтэрч оролдоно уу.');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Хадгалж чадсангүй.');
      // Update matching dropdowns and row templates on the current page as well.
      const roots = [document, ...Array.from(document.querySelectorAll('template[data-row-template]'), item => item.content)];
      roots.forEach(root => root.querySelectorAll('select[data-options-url]').forEach(other => {
        if (other.dataset.optionStage !== select.dataset.optionStage || other.dataset.optionField !== select.dataset.optionField) return;
        if (select.dataset.optionField === 'subcategory') {
          const options = JSON.parse(other.dataset.options || '[]');
          if (!options.some(item => item.code === result.value && item.category === scope)) {
            options.push({code: result.value, label: result.label, category: scope});
            other.dataset.options = JSON.stringify(options);
          }
        }
        if ((other.dataset.optionScope || '') !== scope) return;
        if (result.price !== undefined) {
          const prices = JSON.parse(other.dataset.prices || '{}');
          prices[result.value] = result.price;
          other.dataset.prices = JSON.stringify(prices);
        }
        if (!Array.from(other.options).some(item => item.value === result.value)) {
          const option = new Option(result.label, result.value);
          other.add(option, Array.from(other.options).find(item => item.value === addValue) || null);
        }
      }));
      if (select.multiple) {
        Array.from(select.options).find(option => option.value === result.value).selected = true;
      } else {
        select.value = result.value;
      }
      remember(select);
      select.dispatchEvent(new Event('change', {bubbles: true}));
      dialog.close();
    } catch (failure) {
      error.textContent = failure.message || 'Хадгалж чадсангүй. Дахин оролдоно уу.';
    } finally {
      saving = false;
      save.disabled = false;
    }
  });
});
