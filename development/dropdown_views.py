import hashlib
import json

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Food, Ingredient, Supplier, SharedDropdownOption
from .workflow import GateAccessQuery, context


@login_required
@require_POST
def add_dropdown_option(request):
    from .gate0_typed import Gate0Form
    from .gate1_typed import Gate1Form
    from .gate2_typed import Gate2Form
    from .gate3_typed import Gate3Form
    from .gate0_rows import RowsField

    try:
        data = json.loads(request.body)
        if not isinstance(data, dict): raise ValueError()
        stage, key, scope, label = (data.get(name, '') for name in ('stage', 'field', 'scope', 'label'))
        if not all(isinstance(value, str) for value in (stage, key, scope, label)): raise ValueError()
        label = ' '.join(label.split())
        if not label or label == '__add_option__' or len(label) > (80 if key == 'category' else 200) or len(scope) > 80:
            raise ValueError()
        form_class = {'gate0': Gate0Form, 'gate1': Gate1Form, 'gate2': Gate2Form, 'gate3': Gate3Form}[stage]
        food_id = data.get('food')
        if food_id and (not isinstance(food_id, (str, int)) or not str(food_id).isdigit()): raise ValueError()
    except (ValueError, TypeError, KeyError):
        return JsonResponse({'error': 'Сонголтын нэр болон талбарыг зөв оруулна уу.'}, status=400)

    food = get_object_or_404(Food, pk=food_id) if food_id else None
    permitted = (food.stage == stage and context(request.user, food)['editable']) if food else (
        stage == 'gate0' and (request.user.is_superuser or GateAccessQuery(request.user, stage, 'can_submit')))
    if not permitted:
        return JsonResponse({'error': 'Энэ үе шатыг засах эрх шаардлагатай.'}, status=403)
    if stage in ['gate1','gate2'] and key == 'recipe_ingredient':
        supplier_name = data.get('supplier', '')
        try:
            if not isinstance(supplier_name, str): raise ValueError()
            supplier_name = ' '.join(supplier_name.split())
            if not supplier_name or len(supplier_name) > 160 or len(label) > 160 or scope: raise ValueError()
            price = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2).clean(data.get('price'))
        except (ValueError, TypeError, forms.ValidationError):
            return JsonResponse({'error': 'Орц, нийлүүлэгчийн нэр болон кг үнийг зөв оруулна уу.'}, status=400)
        with transaction.atomic():
            supplier, _ = Supplier.objects.get_or_create(name=supplier_name)
            # Serialize additions for this supplier to avoid duplicate ingredient entries.
            Supplier.objects.select_for_update().get(pk=supplier.pk)
            ingredient, created = Ingredient.objects.get_or_create(name=label, supplier=supplier, unit='kg', defaults={'price': price})
        return JsonResponse({'value': str(ingredient.pk), 'label': str(ingredient), 'price': str(ingredient.price)},
                            status=201 if created else 200)
    form = form_class(food=food, initial={'category': scope})
    field = form.fields.get(key)
    if '.' in key:
        parent, child = key.split('.', 1)
        rows = form.fields.get(parent)
        field = rows.row_form().fields.get(child) if isinstance(rows, RowsField) else None
    if not isinstance(field, forms.ChoiceField) or not isinstance(field.widget, forms.Select):
        return JsonResponse({'error': 'Жагсаалтын талбар олдсонгүй.'}, status=400)
    if field.disabled:
        return JsonResponse({'error': 'Энэ талбар түгжигдсэн байна.'}, status=403)
    if stage == 'gate0' and key == 'subcategory':
        if scope not in dict(form.fields['category'].choices) or not scope:
            return JsonResponse({'error': 'Эхлээд ангилал сонгоно уу.'}, status=400)
    elif scope:
        return JsonResponse({'error': 'Сонголтын ангилал буруу байна.'}, status=400)
    for value, text in field.choices:
        if value and label.casefold() in (str(text).strip().casefold(), str(value).casefold()):
            return JsonResponse({'value': str(value), 'label': str(text)})
    option, created = SharedDropdownOption.objects.get_or_create(
        stage=stage, field=key, scope=scope,
        label_key=hashlib.sha256(label.casefold().encode('utf-8')).hexdigest(),
        defaults={'label': label})
    return JsonResponse({'value': option.label, 'label': option.label}, status=201 if created else 200)
