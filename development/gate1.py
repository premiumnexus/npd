"""Gate 1 inputs, with data types and validation to be agreed later."""
from django import forms
from django.db import transaction

FIELDS = [
    ('1.1','trial_log','Туршилтын бүртгэл (мөр)'),
    ('1.2','recipe_version_internal_tasting','Жорын хувилбарын дугаар'),
    ('2.1','taster_count','Амтлагчдын тоо (5-аас доошгүй)'),
    ('2.2','tasting_score','Дотоод амталгааны үнэлгээ (1–5)'),
    ('2.4','consumer_test','Туршилтад оролцсон хэрэглэгчдийн тоо'),
    ('2.5','consumer_liking','Таалагдсан үнэлгээ (1–9)'),
    ('2.6','consumer_would_buy_percent','Зорилтот үнээр худалдан авах хувь (%)'),
    ('1.6','estimated_cogs_vs_limit','Тооцоолсон COGS = орц + савлагаа'),
    ('1.7','cogs_limit','Gate 0 COGS хязгаар (Gate 0 3.10-аас)'),
    ('1.8','cogs_gap_percent','COGS зөрүү (%)'),
    ('1.9','cogs_status','COGS төлөв'),
    ('1.10','typed_cogs','COGS гараар оруулах (₮)'),
    ('1.10','typed_cogs_reason','COGS гараар оруулах шалтгаан'),
    ('1.11','cogs_reason','Amber / Red шалтгаан'),
    ('1.12','cogs_action','Amber / Red үед авах арга хэмжээ'),
    ('3.1','raw_material_spec_price_moq_second_source','Шинэ эсвэл өөрчлөгдсөн түүхий эд'),
    ('4.1','capacity_equipment_fit','Үйлдвэрлэлийн шугам'),
    ('4.2','capacity_units_day','Хүчин чадал (ширхэг/өдөр)'),
    ('4.3','capacity_constraint','Хязгаарлалт байгаа эсэх'),
    ('4.4','constraint_details','Хязгаарлалтын тайлбар'),
    ('6.1','qa_requirements_issued','Хориглосон орцыг шалгасан эсэх'),
    ('6.2','process_flow_ccp_issued','Процессын урсгал ба CCP шаардлага гаргасан эсэх'),
    ('6.3','fridge_check_72h','Хадгалалтын шалгалтын үр дүн'),
    ('6.4','tested_in_actual_packaging','Бодит савлагаанд шалгасан эсэх'),
    ('6.5','fridge_check_date','Шалгасан огноо'),
    ('6.7','shelf_life_test_plan','Лаборатори'),
    ('6.8','shelf_life_test_days','Туршилтын хугацаа (хоног)'),
    ('6.9','shelf_life_result_due','Үр дүн гарах огноо'),
    ('5.1','packaging_label_concept','Савлагаа (одоо байгаа эсвэл шинэ)'),
    ('5.2','packaging_unit_price','Нэгжийн үнэ (₮)'),
    ('5.3','pack_material','Савлагааны материал'),
    ('5.4','pack_size','Савлагааны хэмжээ'),
    ('5.5','material_certificate','Хүнстэй харьцах материалын гэрчилгээ байгаа эсэх'),
    ('5.6','packaging_supplier','Шинэ савлагаа бол: нийлүүлэгч'),
    ('5.6','packaging_moq','Шинэ савлагаа бол: MOQ'),
    ('5.6','packaging_lead_days','Шинэ савлагаа бол: нийлүүлэх хугацаа (хоног)'),
    ('7.1','marketing_name','Кампанит ажлын нэр'),
    ('7.2','marketing_key_message','Гол мессеж'),
    ('7.3','marketing_brief','Нэвтрүүлэлтийн маркетингийн санаа'),
]

FILE_SLOTS = [
    ('G1-F1','Амталгааны бүртгэл (файл)'),
    ('G1-F2','Хэрэглэгчийн туршилтын үр дүн (файл)'),
    ('G1-F3','Нийлүүлэгчийн өртгийн тооцоо эсвэл үнийн санал'),
    ('G1-F4','Түүхий эдийн техникийн тодорхойлолт'),
    ('G1-F5','Шалгалтын бүртгэл, зураг (файл)'),
    ('G1-F6','QA эрсдэлийн үнэлгээ (файл)'),
    ('G1-F7','Савлагааны концепц, mock-up'),
    ('G1-F8','Бүтээгдэхүүний зураг'),
    ('G1-F9','COGS тооцоо (Excel)'),
    ('G1-F10','Нэвтрүүлэлтийн маркетингийн санааны файл'),
]

def file_slots(food):
    files=list(food.gate1_files.select_related('uploader'))
    marketing_files=list(food.activities.filter(attachment_stage='gate1',attachment_slot='G1-F10').select_related('actor').order_by('-created','-pk'))
    return [{'key':key,'label':label,'number':{'G1-F1':'2.3','G1-F2':'2.7','G1-F3':'1.13','G1-F4':'3.1','G1-F5':'6.6','G1-F6':'6.10','G1-F7':'5.7','G1-F10':'7.4'}.get(key,key),'inline':key in ('G1-F1','G1-F2','G1-F3','G1-F4','G1-F5','G1-F6','G1-F7','G1-F8','G1-F9','G1-F10'),'files':marketing_files if key=='G1-F10' else [item for item in files if item.slot_code==key]} for key,label in FILE_SLOTS]

@transaction.atomic
def save_slot_file(food,user,key,uploaded):
    from .models import Activity, Gate1, Gate1File
    label = dict(FILE_SLOTS)[key]
    if key != 'G1-F10':
        activity = Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,label))
        return Gate1File.objects.create(development=food,slot_code=key,file=uploaded,
            original_filename=uploaded.name[:255],uploader=user,uploaded_at=activity.created,activity=activity)
    activity = Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,label),attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage='gate1',attachment_slot=key)
    Gate1.objects.update_or_create(development_id=food.pk, defaults={
        'marketing_idea_file': activity.attachment.name,
        'marketing_idea_filename': activity.attachment_name,
        'marketing_idea_uploaded_by_id': activity.actor_id,
        'marketing_idea_uploaded_at': activity.created,
    })
    return activity

from .gate1_typed import Gate1Form

def initial_brief(food):
    from .gate_storage import read_gate, serialize
    data=read_gate(1,food)
    from .gate1_typed import cost_comparison
    data.update({key:serialize(value) for key,value in cost_comparison(food,data.get('typed_cogs')).items()})
    return data


@transaction.atomic
def save_brief(food,data,user=None):
    from .gate_storage import save_gate
    payload=dict(data)
    price=payload.pop('packaging_unit_price',None)
    if price is not None:
        price=food._meta.get_field('packaging').clean(price,food)
        food.packaging=price
        food.save(update_fields=['packaging','updated'])
        from .gate1_typed import cost_comparison
        payload.update(cost_comparison(food,data.get('typed_cogs')))
    for key,slot in [('trial_log','G1-F1'),('raw_material_spec_price_moq_second_source','G1-F4')]:
        if not isinstance(payload.get(key),list): continue
        payload[key]=[dict(row) if isinstance(row,dict) else row for row in payload[key]]
        for row in payload[key]:
            if not isinstance(row,dict): continue
            uploaded=row.pop('file',None)
            if uploaded:
                if user is None: raise ValueError('An actor is required to upload row attachments.')
                row['attachment']=save_slot_file(food,user,slot,uploaded).pk
    return save_gate(1,food,payload)
