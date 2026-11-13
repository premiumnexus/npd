"""Frozen conversion for migration 0034; do not change for future schemas."""
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
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

def forwards(apps, schema_editor):
    alias=schema_editor.connection.alias
    Food=apps.get_model('development','Food')
    Archive=apps.get_model('development','GateDataArchive')
    parents={row.pk:row for row in Food.objects.using(alias).all()}
    for number in range(4):
        Gate=apps.get_model('development','Gate%s'%number)
        Gate.objects.using(alias).bulk_create([
            Gate(development_id=pk,**({'product_name':parent.name,'category':parent.category} if number==0 else {}))
            for pk,parent in parents.items()
        ])
        Legacy=apps.get_model('development','Gate%sBrief'%number)
        for old in Legacy.objects.using(alias).all().iterator():
            issues=[]
            try:
                payload=json.loads(old.data)
                if not isinstance(payload,dict):raise ValueError('Expected object')
            except (ValueError,TypeError):
                payload=None
                issues.append({'reason':'invalid_json'})
            if old.food_id not in parents:
                issues.append({'reason':'missing_development'})
            elif payload is not None:
                _,conversion_issues=persist(apps,alias,number,old.food_id,payload)
                issues.extend(conversion_issues)
            Archive.objects.using(alias).create(
                gate='gate%s'%number,source_pk=old.pk,development_id=old.food_id,
                raw_data=old.data,issues=json.dumps(issues),
                reviewed_at=timezone.now() if not issues else None,
            )
    copy_admin_permissions(apps,alias)


def copy_admin_permissions(apps,alias):
    # Preserve existing Django-admin grants under the replacement model names.
    ContentType=apps.get_model('contenttypes','ContentType')
    Permission=apps.get_model('auth','Permission')
    Group=apps.get_model('auth','Group')
    User=apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    for number in range(4):
        old_type=ContentType.objects.using(alias).filter(app_label='development',model='gate%sbrief'%number).first()
        if old_type is None:continue
        new_type,_=ContentType.objects.using(alias).get_or_create(app_label='development',model='gate%s'%number)
        for action in ['add','change','delete','view']:
            old_permission=Permission.objects.using(alias).filter(content_type=old_type,codename='%s_gate%sbrief'%(action,number)).first()
            if old_permission is None:continue
            new_permission,_=Permission.objects.using(alias).get_or_create(content_type=new_type,codename='%s_gate%s'%(action,number),defaults={'name':'Can %s gate %s'%(action,number)})
            permissions=[new_permission]
            child_actions=['view','add','change','delete'] if action=='change' else [action]
            for child in list(SELECTIONS.get(number,{}).values())+list(ROWS.get(number,{}).values()):
                child_type,_=ContentType.objects.using(alias).get_or_create(app_label='development',model=child.lower())
                for child_action in child_actions:
                    permission,_=Permission.objects.using(alias).get_or_create(content_type=child_type,codename='%s_%s'%(child_action,child.lower()),defaults={'name':'Can %s %s'%(child_action,child)})
                    permissions.append(permission)
            for group in Group.objects.using(alias).filter(permissions=old_permission):
                group.permissions.add(*permissions)
            for user in User.objects.using(alias).filter(user_permissions=old_permission):
                user.user_permissions.add(*permissions)


def backwards(apps, schema_editor):
    alias=schema_editor.connection.alias
    Archive=apps.get_model('development','GateDataArchive')
    for number in range(4):
        Legacy=apps.get_model('development','Gate%sBrief'%number)
        Gate=apps.get_model('development','Gate%s'%number)
        # Exact pre-migration originals include retired values and orphan records.
        for old in Archive.objects.using(alias).filter(gate='gate%s'%number,source_pk__gt=0):
            Legacy.objects.using(alias).update_or_create(pk=old.source_pk,defaults={'food_id':old.development_id,'data':old.raw_data})
        for record in Gate.objects.using(alias).all():
            previous=Legacy.objects.using(alias).filter(food_id=record.pk).first()
            try:payload=json.loads(previous.data) if previous else {}
            except (ValueError,TypeError):payload={}
            if not isinstance(payload,dict):payload={}
            originals=list(Archive.objects.using(alias).filter(gate='gate%s'%number,development_id=record.pk).order_by('pk'))
            unconverted={}
            for source in originals:
                try:
                    raw=json.loads(source.raw_data)
                    if not isinstance(raw,dict):continue
                    if source.reviewed_at is None:
                        for issue in json.loads(source.issues or '[]'):
                            key=issue.get('field')
                            if key and issue.get('reason','').startswith('invalid_'):
                                unconverted[key]=raw.get(key)
                except (ValueError,TypeError):continue
            for field in scalar_fields(Gate):
                value=getattr(record,field.name)
                payload[field.name]=unconverted[field.name] if field.name in unconverted else serialize(value)
            for mapping,selection in [(SELECTIONS.get(number,{}),True),(ROWS.get(number,{}),False)]:
                for key,child_name in mapping.items():
                    if key in unconverted:
                        payload[key]=unconverted[key]
                        continue
                    Child=apps.get_model('development',child_name)
                    rows=Child.objects.using(alias).filter(gate_id=record.pk).order_by('position','pk')
                    payload[key]=[row.value for row in rows] if selection else [{f.name:serialize(getattr(row,f.name)) for f in scalar_fields(Child)} for row in rows]
            # Retain exact originals even after the archive table is reversed away.
            payload['_relational_source_archives']=[source.raw_data for source in originals]
            Legacy.objects.using(alias).update_or_create(food_id=record.pk,defaults={'data':json.dumps(payload,ensure_ascii=False,default=str)})
