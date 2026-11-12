"""Shared choices for gate dropdowns, including repeatable material rows."""
import json

from django import forms
from django.urls import reverse

from .models import SharedDropdownOption
from .dropdown_widgets import AddableSelect, AddableSelectMultiple


def apply_options(form, stage, prefix=''):
    form.option_stage = stage
    saved = list(SharedDropdownOption.objects.filter(stage=stage))
    category = (form.data.get('category') if form.is_bound else form.initial.get('category')) or ''
    for name, field in form.fields.items():
        if not isinstance(field, forms.ChoiceField) or not isinstance(field.widget, forms.Select):
            continue
        key = prefix + name
        scope = category if stage == 'gate0' and name == 'subcategory' else ''
        additions = [item for item in saved if item.field == key]
        choices = list(field.choices)
        existing = {str(value) for value, label in choices}
        choices.extend((item.label, item.label) for item in additions
                       if item.scope == scope and item.label not in existing)
        widget_class = AddableSelectMultiple if field.widget.allow_multiple_selected else AddableSelect
        field.widget = widget_class(attrs=field.widget.attrs, choices=choices)
        field.choices = choices
        field.widget.attrs.update({
            'data-options-url': reverse('add_dropdown_option'),
            'data-option-stage': stage,
            'data-option-field': key,
            'data-option-scope': scope,
            'data-option-food': str(getattr(getattr(form, 'food', None), 'pk', '') or ''),
        })
        if stage == 'gate0' and name == 'subcategory':
            options = json.loads(field.widget.attrs.get('data-options', '[]'))
            options.extend({'code': item.label, 'label': item.label, 'category': item.scope}
                           for item in additions)
            field.widget.attrs['data-options'] = json.dumps(options, ensure_ascii=False)
