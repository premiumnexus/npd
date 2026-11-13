"""Typed gate persistence. JSON is used only for immutable legacy archives."""
import json
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


SELECTIONS = {
    0: {'improvement_reasons': 'Gate0ImprovementReason', 'daypart': 'Gate0Daypart',
        'first_food_safety_risk': 'Gate0Allergen', 'high_risk_inputs': 'Gate0HighRiskInput'},
    3: {'lesson_tags': 'Gate3LessonTag'},
}
ROWS = {
    0: {'competitor_benchmark': 'Gate0Competitor', 'analog_skus_sales_target': 'Gate0AnalogSKU',
        'cannibalisation': 'Gate0Cannibalisation'},
    1: {'raw_material_spec_price_moq_second_source': 'Gate1Material'},
}


def serialize(value):
    if isinstance(value, Decimal):
        return format(value, 'f').rstrip('0').rstrip('.') if value.as_tuple().exponent < 0 else format(value, 'f')
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def coerce(field, value):
    if value is None or value == '' and not isinstance(field, (models.CharField, models.TextField)):
        return None
    if isinstance(value, (list, dict, tuple)):
        raise ValidationError('Expected a scalar value.')
    if isinstance(field, models.IntegerField):
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value():
            raise ValidationError('Expected a whole number.')
        value = int(number)
    if isinstance(field, models.DecimalField):
        value = field.to_python(Decimal(str(value)))
        if value is not None and field.decimal_places >= 18:
            with localcontext() as context:
                context.prec = max(field.max_digits, 50)
                value = value.quantize(Decimal(1).scaleb(-field.decimal_places))
    return field.clean(value, None)


def scalar_fields(model):
    return [field for field in model._meta.concrete_fields if not field.primary_key
            and field.name not in ('gate', 'position')]


def persist(registry, alias, gate, development_id, payload):
    """Also usable by the frozen migration copy with historical model classes."""
    model = registry.get_model('development', 'Gate%s' % gate)
    fields = scalar_fields(model)
    issues, values = [], {}
    known = {field.name for field in fields} | set(SELECTIONS.get(gate, {})) | set(ROWS.get(gate, {}))
    for key in payload:
        if key not in known and not key.startswith('_'):
            issues.append({'field': key, 'reason': 'retired_or_unknown'})
    for field in fields:
        try:
            values[field.name] = coerce(field, payload.get(field.name))
        except (ValidationError, ValueError, TypeError, InvalidOperation, OverflowError):
            values[field.name] = None
            issues.append({'field': field.name, 'reason': 'invalid_scalar'})
    record, _ = model.objects.using(alias).update_or_create(development_id=development_id, defaults=values)
    for mapping, selection in [(SELECTIONS.get(gate, {}), True), (ROWS.get(gate, {}), False)]:
        for name, child_name in mapping.items():
            child = registry.get_model('development', child_name)
            child.objects.using(alias).filter(gate_id=development_id).delete()
            rows = payload.get(name, [])
            if name == 'daypart' and isinstance(rows, str):
                rows = [rows] if rows else []
            if rows in (None, ''): rows = []
            if not isinstance(rows, list):
                issues.append({'field': name, 'reason': 'invalid_collection'})
                continue
            pending = []
            for position, item in enumerate(rows):
                source = {'value': item} if selection else item
                if not isinstance(source, dict):
                    issues.append({'field': name, 'position': position, 'reason': 'invalid_row'})
                    continue
                data = {}
                for field in scalar_fields(child):
                    try:
                        data[field.name] = coerce(field, source.get(field.name))
                    except (ValidationError, ValueError, TypeError, InvalidOperation, OverflowError):
                        data[field.name] = None
                        issues.append({'field': name, 'position': position, 'column': field.name, 'reason': 'invalid_scalar'})
                if selection and data.get('value') is None:
                    continue
                pending.append(child(gate_id=development_id, position=position, **data))
            child.objects.using(alias).bulk_create(pending)
    return record, issues


@transaction.atomic
def ensure_gate_rows(food):
    """One primary key, allocated only by Food, is shared by all four gate rows."""
    for gate in range(4):
        defaults = {'product_name': food.name, 'category': food.category} if gate == 0 else {}
        apps.get_model('development', 'Gate%s' % gate).objects.get_or_create(development_id=food.pk, defaults=defaults)


@transaction.atomic
def save_gate(gate, food, payload):
    alias = food._state.db or 'default'
    record, issues = persist(apps, alias, gate, food.pk, payload)
    archive = apps.get_model('development', 'GateDataArchive')
    archive.objects.using(alias).filter(gate='gate%s' % gate, development_id=food.pk, reviewed_at__isnull=True).update(reviewed_at=timezone.now())
    if issues or payload.get('_legacy_free_text'):
        archive.objects.using(alias).create(
            gate='gate%s' % gate, source_pk=-time.time_ns(), development_id=food.pk,
            raw_data=json.dumps(payload, ensure_ascii=False, default=str),
            issues=json.dumps(issues), reviewed_at=None if issues else timezone.now(),
        )
    return record


def read_record(gate, record):
    values = {field.name: serialize(getattr(record, field.name)) for field in scalar_fields(type(record))}
    for mapping, selection in [(SELECTIONS.get(gate, {}), True), (ROWS.get(gate, {}), False)]:
        for key, name in mapping.items():
            child = apps.get_model('development', name)
            rows = child.objects.filter(gate_id=record.pk).order_by('position', 'pk')
            values[key] = [item.value for item in rows] if selection else [
                {field.name: serialize(getattr(item, field.name)) for field in scalar_fields(child)} for item in rows]
    legacy = {}
    for archive in apps.get_model('development', 'GateDataArchive').objects.filter(gate='gate%s' % gate, development_id=record.pk).order_by('pk'):
        try:
            original = json.loads(archive.raw_data)
            if not isinstance(original, dict): continue
            legacy.update(original.get('_legacy_free_text') or {})
            if original.get('_schema_version') not in (2, 3): legacy.update(original)
            issues = json.loads(archive.issues or '[]')
            for issue in issues:
                if issue.get('reason') == 'retired_or_unknown':
                    legacy[issue['field']] = original.get(issue['field'])
            if archive.reviewed_at is None:
                for issue in issues:
                    key = issue.get('field')
                    if issue.get('reason') in ('invalid_scalar', 'invalid_collection') and key in values:
                        values[key] = original.get(key)
        except (ValueError, TypeError, AttributeError):
            continue
    if legacy: values['_legacy_free_text'] = legacy
    values['_schema_version'] = 3
    return values


def read_gate(gate, food):
    record = apps.get_model('development', 'Gate%s' % gate).objects.filter(development_id=food.pk).first()
    if record is None:
        return {'product_name': food.name, 'category': food.category} if gate == 0 else {}
    return read_record(gate, record)
