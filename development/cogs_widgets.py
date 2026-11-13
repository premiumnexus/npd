from django import forms


COGS_STATUS_LABELS = {
    'Green': 'Ногоон',
    'Amber': 'Шар',
    'Red': 'Улаан',
}


def status_label(value):
    return COGS_STATUS_LABELS.get(value, 'Хүлээгдэж байна')


class COGSStatusWidget(forms.TextInput):
    def get_context(self, name, value, attrs):
        context = super().get_context(name, status_label(value), attrs)
        context['widget']['attrs'].update({
            'data-cogs-status-field': True,
            'data-cogs-status': value if value in COGS_STATUS_LABELS else 'Pending',
        })
        return context
