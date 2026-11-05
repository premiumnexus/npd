"""Gate 2 inputs; data types and business rules will be defined later."""
import json
from django import forms

FIELDS = [
    ('2.1','mass_trial_result','Масс туршилтын үр дүн'),
    ('2.2','final_cogs_invoice_price','Эцсийн COGS ба нэхэмжлэхийн үнэ'),
    ('2.3','lab_results_approved_shelf_life','Лабын үр дүн'),
    ('2.4','final_technology_transfer_document','Технологи шилжүүлэх баримт (эцсийн)'),
    ('2.5','label_check','Шошгоны шалгалт'),
    ('2.6','barcode_system_registration','Баркод, системийн бүртгэл'),
    ('2.7','allocation','Хуваарилалт'),
    ('2.8','supply_readiness','Нийлүүлэлтийн бэлэн байдал'),
    ('2.9','marketing_plan','Маркетингийн төлөвлөгөө'),
    ('2.10','quality_tolerance_baseline','Чанарын зөвшөөрөх хүрээ'),
    ('2.11','day45_target_confirmed','45 хоногийн зорилт баталгаажуулах'),
    ('2.12','launch_date','Нэвтрүүлэх огноо'),
]

FILE_SLOTS = [
    ('G2-F1','Масс туршилтын бүртгэл, checklist'),
    ('G2-F2','Нийлүүлэгчийн эцсийн үнийн санал'),
    ('G2-F3','Лабын тайлан'),
    ('G2-F4','Хадгалах хугацааны тайлан'),
    ('G2-F5','Технологи шилжүүлэх баримт (гарын үсэгтэй)'),
    ('G2-F6','HACCP / CCP төлөвлөгөө'),
    ('G2-F7','Шошгоны эцсийн загвар'),
    ('G2-F8','Савлагааны эцсийн спец'),
    ('G2-F9','Маркетингийн төлөвлөгөө'),
    ('G2-F10','Хуваарилалтын төлөвлөгөө'),
    ('G2-F11','COGS эцсийн тооцоо (Excel)'),
]

def file_slots(food):
    files=list(food.activities.filter(attachment_stage='gate2').exclude(attachment_slot=''))
    return [{'key':key,'label':label,'files':[item for item in files if item.attachment_slot==key]} for key,label in FILE_SLOTS]

def save_slot_file(food,user,key,uploaded):
    from .models import Activity
    Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,dict(FILE_SLOTS)[key]),attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage='gate2',attachment_slot=key)

from .gate2_typed import Gate2Form

def initial_brief(food):
    from .models import Gate2Brief
    brief=Gate2Brief.objects.filter(food=food).first()
    return json.loads(brief.data) if brief else {}

def save_brief(food,data):
    from .models import Gate2Brief
    previous=initial_brief(food)
    payload=dict(data)
    payload['_schema_version']=2
    if previous.get('_schema_version') != 2: payload['_legacy_free_text']=previous
    elif previous.get('_legacy_free_text'): payload['_legacy_free_text']=previous['_legacy_free_text']
    Gate2Brief.objects.update_or_create(food=food,defaults={'data':json.dumps(payload,ensure_ascii=False,default=str)})
