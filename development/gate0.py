"""Gate 0 brief: free-text fields until data types and rules are agreed."""
from django import forms
import json

FIELDS = [
    ('0.1','product_name','Бүтээгдэхүүний нэр'),
    ('0.1','category','Ангилал'),
    ('0.1','subcategory','Дэд ангилал'),
    ('0.2','product_type','Шинэ эсвэл сайжруулалт'),
    ('0.3','improvement_reason','Сайжруулалтын шалтгаан'),
    ('0.4','product_role','Бүтээгдэхүүний үүрэг'),
    ('0.5','target_customer_occasion','Зорилтот хэрэглэгч, хэрэглээний үе'),
    ('0.6','customer_need_evidence','Хэрэглээний нотолгоо'),
    ('0.7','competitor_benchmark','Өрсөлдөгчийн жишиг'),
    ('0.8','target_shelf_price','Зорилтот тавиурын үнэ (НӨАТ-тай)'),
    ('0.9','cu_margin','CU-ийн ашгийн хувь'),
    ('0.10','vendor_rebate','Rebate (буцаан олголт) %'),
    ('0.11','producer','Үйлдвэрлэгч'),
    ('0.12','vendor_margin','Нийлүүлэгчийн ашгийн хувь'),
    ('0.13','cogs_limit','COGS-ийн дээд хязгаар'),
    ('0.14','analog_skus_sales_target','Жишиг SKU ба борлуулалтын зорилт'),
    ('0.15','store_scope','Дэлгүүрийн хамрах хүрээ'),
    ('0.16','cannibalisation','Каннибализаци'),
    ('0.17','raw_materials_supply_risk','Гол түүхий эд, нийлүүлэлтийн эрсдэл'),
    ('0.18','first_capacity_check','Хүчин чадлын анхны үнэлгээ'),
    ('0.19','first_food_safety_risk','Хүнсний аюулгүй байдлын анхны эрсдэл'),
    ('0.20','technical_risk_measure','Хэмжих техникийн эрсдэл'),
    ('0.21','day45_success_criteria','45 хоногийн амжилтын шалгуур'),
    ('0.22','planned_launch_date','Төлөвлөсөн нэвтрүүлэх огноо'),
]

FILE_SLOTS = [
    ('G0-F1','Хэрэглэгчийн нотолгоо (судалгаа, POS extract, дэлгүүрийн хүсэлт)'),
    ('G0-F2','Жишиг бүтээгдэхүүний зураг, үнэ'),
    ('G0-F3','Концепц дэлгэрэнгүй'),
    ('G0-F4','Одоогийн SKU-ийн мэдээлэл (борлуулалт, гомдол, write-off)'),
]

def file_slots(food=None):
    files = list(food.activities.exclude(attachment_slot='')) if food else []
    return [{'key':key,'label':label,'files':[item for item in files if item.attachment_slot==key]} for key,label in FILE_SLOTS]

def save_slot_file(food,user,key,uploaded):
    from .models import Activity
    Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,dict(FILE_SLOTS)[key]),attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage='gate0',attachment_slot=key)

from .gate0_typed import Gate0Form

def initial_brief(food):
    from .models import Gate0Brief
    saved = Gate0Brief.objects.filter(food=food).first()
    return json.loads(saved.data) if saved else {'product_name':food.name,'category':food.category}

def save_brief(food,data):
    from .models import Gate0Brief
    previous=initial_brief(food)
    payload=dict(data)
    from .target_costing import calculate
    payload.update(calculate(data))
    payload['_schema_version']=2
    if previous.get('_schema_version') != 2:
        payload['_legacy_free_text']=previous
    elif previous.get('_legacy_free_text'):
        payload['_legacy_free_text']=previous['_legacy_free_text']
    Gate0Brief.objects.update_or_create(food=food,defaults={'data':json.dumps(payload,ensure_ascii=False,default=str)})
    food.name = (data.get('product_name') or 'Нэргүй бүтээгдэхүүн')[:160]
    food.category = data.get('category','')[:80]
    food.save(update_fields=['name','category','updated'])
