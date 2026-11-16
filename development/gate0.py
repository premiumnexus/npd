"""Gate 0 brief: free-text fields until data types and rules are agreed."""
from django import forms

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
    ('0.20','technical_risk_measure','Шинжилгээ, хэмжилтээр шалгах технологийн эрсдэл'),
    ('0.21','day45_success_criteria','45 хоногийн амжилтын шалгуур'),
    ('0.22','planned_launch_date','Төлөвлөсөн нэвтрүүлэх огноо'),
]

FILE_SLOTS = [
    ('G0-F1','Хэрэглэгчийн нотолгоо (судалгаа, POS extract, дэлгүүрийн хүсэлт)'),
    ('G0-F2','Жишиг бүтээгдэхүүний зураг, үнэ'),
    ('G0-F3','Концепц дэлгэрэнгүй'),
    ('G0-F4','Одоогийн SKU-ийн мэдээлэл (борлуулалт, гомдол, акт)'),
]

def file_slots(food=None):
    files = list(food.gate0_files.select_related('uploader')) if food else []
    return [{'key':key,'label':label,'files':[item for item in files if item.slot_code==key]} for key,label in FILE_SLOTS]

def save_slot_file(food,user,key,uploaded):
    from .models import Activity,Gate0File
    from django.db import transaction
    label=dict(FILE_SLOTS)[key]
    with transaction.atomic():
        activity=Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,label))
        return Gate0File.objects.create(development=food,slot_code=key,file=uploaded,
            original_filename=uploaded.name[:255],uploader=user,uploaded_at=activity.created,activity=activity)

from .gate0_typed import Gate0Form

def initial_brief(food):
    from .gate_storage import read_gate, serialize
    from .target_costing import calculate
    data=read_gate(0,food)
    if any(data.get(key) is not None for key in ['target_shelf_price','cu_margin','vendor_rebate','vendor_margin']):
        data.update({key:serialize(value) for key,value in calculate(data,data.get('vat_percent')).items()})
    return data


from django.db import transaction

@transaction.atomic
def save_brief(food,data):
    from .gate_storage import save_gate
    from .target_costing import calculate
    payload=dict(data)
    payload.update(calculate(data))
    record=save_gate(0,food,payload)
    food.name=(data.get('product_name') or 'Нэргүй бүтээгдэхүүн')[:160]
    food.category=(data.get('category') or '')[:80]
    food.save(update_fields=['name','category','updated'])
    return record
