"""Gate 2 inputs; data types and business rules will be defined later."""
from django import forms
from django.db import transaction

FIELDS = [
    ('2.1','mass_trial_result','Масс туршилтын үр дүн'),
    ('2.2','final_cogs_invoice_price','Эцсийн COGS ба нэхэмжлэхийн үнэ'),
    ('2.3','lab_results_approved_shelf_life','Лабын үр дүн'),
    ('2.4','final_technology_transfer_document','Технологи шилжүүлэх баримт (эцсийн)'),
    ('2.5','label_checked','Шошгоны шалгалт'),
    ('2.6','barcode_system_registration','Баркод, системийн бүртгэл'),
    ('2.7','allocation','Хуваарилалт'),
    ('2.8','supply_readiness','Нийлүүлэлтийн бэлэн байдал'),
    ('2.9','marketing_plan','Маркетингийн төлөвлөгөө'),
    ('2.10','quality_tolerance_baseline','Чанарын зөвшөөрөх хүрээ'),
    ('2.11','day45_target_confirmed','45 хоногийн зорилт баталгаажуулах'),
    ('2.12','launch_date','Нэвтрүүлэх огноо'),
]

FILE_SLOTS = [
    ('G2-F1','Масс туршилтын бүртгэл'),
    ('G2-F2','Нийлүүлэгчийн эцсийн үнийн санал'),
    ('G2-F3','Лабораторийн тайлан'),
    ('G2-F4','Хадгалах хугацааны тайлан'),
    ('G2-F5','Технологи шилжүүлэх баримт (гарын үсэгтэй)'),
    ('G2-F6','HACCP / CCP төлөвлөгөө'),
    ('G2-F7','Шошгоны эцсийн загвар'),
    ('G2-F8','Савлагааны эцсийн Техникийн тодорхойлолт'),
    ('G2-F9','Маркетингийн төлөвлөгөө'),
    ('G2-F10','Хуваарилалтын төлөвлөгөө'),
    ('G2-F11','COGS эцсийн тооцоо (Excel)'),
    ('G2-F12','ISF Manual'),
    ('G2-F13','Чанарын стандарт'),
]

def available_file_slots(food):
    from .gate0 import initial_brief as gate0_brief
    isf=gate0_brief(food).get('category')=='ISF'
    return [(key,label) for key,label in FILE_SLOTS if key!='G2-F12' or isf]


def file_slots(food):
    files=list(food.gate2_files.select_related('uploader'))
    inline_files=list(food.activities.filter(attachment_stage='gate2',attachment_slot__in=['G2-F12','G2-F13']).select_related('actor').order_by('-created','-pk'))
    inline_numbers={'G2-F12':'2.12','G2-F13':'2.10'}
    return [{'key':key,'label':label,'number':inline_numbers.get(key,key),'inline':key in inline_numbers,'files':[item for item in inline_files if item.attachment_slot==key] if key in inline_numbers else [item for item in files if item.slot_code==key]} for key,label in available_file_slots(food)]

@transaction.atomic
def save_slot_file(food,user,key,uploaded):
    from .models import Activity, Gate2, Gate2File
    label=dict(available_file_slots(food))[key]
    if key in ('G2-F12','G2-F13'):
        activity=Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,label),attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage='gate2',attachment_slot=key)
        if key == 'G2-F13':
            Gate2.objects.update_or_create(development_id=food.pk, defaults={
                'quality_standard_file': activity.attachment.name,
                'quality_standard_filename': activity.attachment_name,
                'quality_standard_uploaded_by_id': activity.actor_id,
                'quality_standard_uploaded_at': activity.created,
            })
        return activity
    activity=Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,label))
    return Gate2File.objects.create(development=food,slot_code=key,file=uploaded,
        original_filename=uploaded.name[:255],uploader=user,uploaded_at=activity.created,activity=activity)

from .gate2_typed import Gate2Form

def initial_brief(food):
    from .gate_storage import read_gate, serialize
    data=read_gate(2,food)
    from .gate2_typed import derived_values
    data.update({key:serialize(value) for key,value in derived_values(food,None,data.get('launch_date'),data.get('vendor_invoice_price')).items()})
    return data


def save_brief(food,data):
    from .gate_storage import save_gate
    return save_gate(2,food,data)
