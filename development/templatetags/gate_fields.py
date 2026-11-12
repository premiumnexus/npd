import copy
import re

from django import forms, template
from development.dropdown_widgets import AddableSelect

register = template.Library()


class PlaceholderSelect(AddableSelect):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value == '':
            option['attrs'].update(disabled=True, hidden=True)
        return option


@register.simple_tag
def gate_widget(bound_field):
    """Render gate guidance inside the control without changing its value."""
    hint = re.sub(r'^(?:\d+\.\d+|VAT|C\d+)\s*·\s*', '', str(bound_field.help_text)).strip()
    widget = copy.deepcopy(bound_field.field.widget)
    if bound_field.name == 'evidence_level':
        widget.attrs['aria-describedby'] = f'{bound_field.auto_id}_reminder'
    if hint:
        widget.attrs.update(placeholder=hint, title=hint)
        if isinstance(widget, forms.Select) and not widget.allow_multiple_selected:
            widget = PlaceholderSelect(attrs=widget.attrs, choices=[
                (value, hint if value == '' else label)
                for value, label in widget.choices
            ])
            widget.attrs['data-gate-placeholder'] = True
    return bound_field.as_widget(widget=widget)
