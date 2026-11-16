"""Gate 1 inputs, with data types and validation to be agreed later."""
from django import forms
from django.db import transaction

FIELDS = [
    ('1.1','recipe_version_internal_tasting','Жорын хувилбар, дотоод амталгаа'),
    ('1.2','consumer_test','Хэрэглэгчийн Туршилт'),
    ('1.3','estimated_cogs_vs_limit','Тооцоолсон COGS vs хязгаар'),
    ('1.4','raw_material_spec_price_moq_second_source','Түүхий эдийн Техникийн тодорхойлолт, үнэ, MOQ, Нийлүүлэлтийн өөр эх үүсвэр'),
    ('1.5','capacity_equipment_fit','Хүчин чадал, тоног төхөөрөмжийн нийцэл'),
    ('1.6','fridge_check_72h','72 цагийн хөргөгчийн шалгалт'),
    ('1.7','shelf_life_test_plan','Хадгалах хугацааны Туршилтын төлөвлөгөө'),
    ('1.8','qa_requirements_issued','QA шаардлага гаргасан'),
    ('1.9','packaging_label_concept','Савлагаа, шошгоны концепц'),
    ('1.10','marketing_brief','Маркетингийн бриф'),
]

FILE_SLOTS = [
    ('G1-F1','Амталгааны бүртгэл'),
    ('G1-F2','Хэрэглэгчийн Туршилтын үр дүн'),
    ('G1-F3','Нийлүүлэгчийн өртгийн тооцоо эсвэл үнийн санал'),
    ('G1-F4','Түүхий эдийн техникийн тодорхойлолт'),
    ('G1-F5','72 цагийн шалгалтын бүртгэл, зураг'),
    ('G1-F6','QA эрсдэлийн үнэлгээ'),
    ('G1-F7','Савлагааны концепц, mock-up'),
    ('G1-F8','Бүтээгдэхүүний зураг'),
    ('G1-F9','COGS тооцоо (Excel)'),
    ('G1-F10','Нэвтрүүлэлтийн маркетингийн санааны файл'),
]

def file_slots(food):
    files=list(food.gate1_files.select_related('uploader'))
    marketing_files=list(food.activities.filter(attachment_stage='gate1',attachment_slot='G1-F10').select_related('actor').order_by('-created','-pk'))
    return [{'key':key,'label':label,'number':'1.10' if key=='G1-F10' else key,'inline':key=='G1-F10','files':marketing_files if key=='G1-F10' else [item for item in files if item.slot_code==key]} for key,label in FILE_SLOTS]

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


def save_brief(food,data):
    from .gate_storage import save_gate
    return save_gate(1,food,data)
