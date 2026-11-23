"""Gate 0 brief: free-text fields until data types and rules are agreed."""
from django import forms

FIELDS = [
    ('1.1','product_name','Бүтээгдэхүүний нэр'),
    ('1.2','product_type','Шинэ эсвэл сайжруулалт'),
    ('1.3','category','Ангилал'),
    ('1.4','subcategory','Дэд ангилал'),
    ('1.5','product_role','Бүтээгдэхүүний үүрэг'),
    ('1.6','planned_launch_date','Төлөвлөсөн нэвтрүүлэх огноо'),
    ('0.3','improvement_reason','Сайжруулалтын шалтгаан'),
    ('2.1','customer_segment','Зорилтот хэрэглэгчийн сегмент'),
    ('2.2','target_customer_occasion','Зорилтот хэрэглэгч, хэрэглээний тайлбар'),
    ('2.3','daypart','Хэрэглээний үе'),
    ('2.4','evidence','Нотолгоо'),
    ('3.1','competitor_benchmark','Өрсөлдөгчийн жишиг'),
    ('3.2','target_shelf_price','Зорилтот тавиурын үнэ (НӨАТ-тай)'),
    ('3.3','vat_percent','VAT / НӨАТ (%)'),
    ('3.4','cu_margin','CU-ийн ашгийн хувь'),
    ('3.5','vendor_rebate','Rebate % (0 байж болно)'),
    ('3.6','vendor_margin','Нийлүүлэгчийн ашгийн хувь'),
    ('3.7','price_excl_vat','НӨАТ-гүй үнэ (₮)'),
    ('3.8','max_invoice_price','Нийлүүлэгчийн нэхэмжлэхийн дээд үнэ (₮)'),
    ('3.9','cu_total_margin','Rebate орсон CU нийт ашгийн хувь (%)'),
    ('3.10','cogs_limit','COGS-ийн дээд хязгаар'),
    ('4.1','analog_skus_sales_target','Жишиг SKU'),
    ('4.2','target_units_store_day','Зорилтот APSD (ширхэг / дэлгүүр / өдөр)'),
    ('4.3','store_scope','Дэлгүүрийн хамрах хүрээ'),
    ('4.4','store_cluster','Дэлгүүрийн кластер'),
    ('4.5','store_count','Дэлгүүрийн тоо'),
    ('4.6','cannibalisation','Каннибализаци (мөр): нөлөөлөх SKU · борлуулалтаас авах %'),
    ('4.7','day45_writeoff_percent','45 хоногийн акт %'),
    ('4.8','day45_margin_percent','45 хоногийн актын дараах ашиг % (= 3.9 − 4.7)'),
    ('5.1','producer','Үйлдвэрлэгч'),
    ('5.2','new_supplier','Шинэ нийлүүлэгч байгаа эсэх'),
    ('5.3','raw_materials_supply_risk','Шинэ түүхий эд байгаа эсэх'),
    ('5.4','seasonal_price_swing','Улирлын үнийн хэлбэлзэл байгаа эсэх'),
    ('5.5','moq','Захиалгын доод хэмжээ (MOQ)'),
    ('5.6','first_capacity_check','Нийлүүлэгчийн хүчин чадлын анхны үнэлгээ'),
    ('5.7','capacity_units_day','Нийлүүлэгчийн хүчин чадал (ширхэг/өдөр)'),
    ('6.1','first_food_safety_risk','Харшил үүсгэгч'),
    ('6.2','high_risk_inputs','Өндөр эрсдэлтэй орц'),
    ('6.3','shelf_life_hours','Хадгалах хугацаа (цаг)'),
    ('6.4','technical_risk_measure','Шинжилгээ, хэмжилтээр шалгах технологийн эрсдэл'),
]

FILE_SLOTS = [
    ('G0-F1','Хэрэглэгчийн нотолгоо (судалгаа, POS extract, дэлгүүрийн хүсэлт)'),
    ('G0-F2','Жишиг бүтээгдэхүүний зураг, үнэ'),
    ('G0-F4','Одоогийн SKU-ийн мэдээлэл (борлуулалт, гомдол, акт)'),
]

def file_slots(food=None):
    files = list(food.gate0_files.select_related('uploader')) if food else []
    inline={'G0-F1':('2.4',''),'G0-F2':('3.1',''),'G0-F4':('4.1','')}
    return [{'key':key,'label':label,'inline':key in inline,'number':inline[key][0] if key in inline else key,
             'upload_form_id':inline[key][1] if key in inline else '',
             'files':[item for item in files if item.slot_code==key]} for key,label in FILE_SLOTS]

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
    from .target_costing import calculate,after_writeoff_margin
    data=read_gate(0,food)
    if data.get('shelf_life_hours') is None and isinstance(data.get('shelf_life_days'),int):
        data['shelf_life_hours']=data['shelf_life_days']*24
    if not data.get('evidence'):
        legacy={key:data.get(key,'') for key in ('customer_need_evidence','evidence_level','evidence_reference')}
        if any(legacy.values()): data['evidence']=[legacy]
    if any(data.get(key) is not None for key in ['target_shelf_price','cu_margin','vendor_rebate','vendor_margin']):
        data.update({key:serialize(value) for key,value in calculate(data,data.get('vat_percent')).items()})
        data['day45_margin_percent']=serialize(after_writeoff_margin(data['cu_total_margin'],data.get('day45_writeoff_percent')))
    return data


from django.db import transaction

@transaction.atomic
def save_brief(food,data,user=None):
    from .gate_storage import save_gate
    from .target_costing import calculate,after_writeoff_margin
    payload=dict(data)
    for key,slot in [('evidence','G0-F1'),('competitor_benchmark','G0-F2'),('analog_skus_sales_target','G0-F4')]:
        if not isinstance(payload.get(key),list): continue
        payload[key]=[dict(row) if isinstance(row,dict) else row for row in payload[key]]
        for row in payload[key]:
            if not isinstance(row,dict): continue
            uploaded=row.pop('file',None)
            if uploaded:
                if user is None: raise ValueError('An actor is required to upload row attachments.')
                row['attachment']=save_slot_file(food,user,slot,uploaded).pk
    payload.update(calculate(data))
    if any(data.get(key) is not None for key in ['target_shelf_price','cu_margin','vendor_rebate','vendor_margin']):
        payload['day45_margin_percent']=after_writeoff_margin(payload['cu_total_margin'],data.get('day45_writeoff_percent'))
    record=save_gate(0,food,payload)
    food.name=(data.get('product_name') or 'Нэргүй бүтээгдэхүүн')[:160]
    food.category=(data.get('category') or '')[:80]
    food.save(update_fields=['name','category','updated'])
    return record
