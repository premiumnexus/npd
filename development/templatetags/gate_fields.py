import copy
import re

from django import forms, template
from development.dropdown_widgets import AddableSelect
from development.cogs_widgets import status_label

register = template.Library()
register.filter('cogs_status_label', status_label)

@register.filter
def fields_or_form(fields,form):
    return form if fields is None or fields=='' else fields

@register.filter
def exclude_file_slots(slots,codes):
    excluded=set(codes.split(','))
    return [slot for slot in slots if slot['key'] not in excluded]


@register.filter
def gate_sections(form, numbers):
    sections = numbers.split(',')
    return [field for field in form if field.field.gate_number in sections]


class PlaceholderSelect(AddableSelect):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value == '':
            option['attrs'].update(disabled=True, hidden=True)
        return option


@register.simple_tag
def gate_widget(bound_field, form_id=None):
    """Render gate guidance inside the control without changing its value."""
    hint = re.sub(r'^(?:\d+\.\d+|VAT|C\d+)\s*·\s*', '', str(bound_field.help_text)).strip()
    widget = copy.deepcopy(bound_field.field.widget)
    if form_id:
        widget.attrs['form'] = form_id
    if getattr(bound_field.field,'gate_conditional_required',False):
        widget.attrs.update({'data-required-consumer':True,'aria-required':'true' if bound_field.field.gate_required else 'false'})
    if getattr(bound_field.field,'gate_production_conditional',False):
        widget.attrs.update({'data-required-production':True,'aria-required':'true' if bound_field.field.gate_required else 'false'})
    if hint:
        widget.attrs.update(placeholder=hint, title=hint)
        if isinstance(widget, forms.Select) and not widget.allow_multiple_selected:
            widget = PlaceholderSelect(attrs=widget.attrs, choices=[
                (value, hint if value == '' else label)
                for value, label in widget.choices
            ])
            widget.attrs['data-gate-placeholder'] = True
    return bound_field.as_widget(widget=widget)
