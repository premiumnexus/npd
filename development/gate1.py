"""Gate 1 inputs, with data types and validation to be agreed later."""
import json
from django import forms

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
    files=list(food.activities.filter(attachment_stage='gate1').exclude(attachment_slot=''))
    return [{'key':key,'label':label,'number':'1.10' if key=='G1-F10' else key,'inline':key=='G1-F10','files':[item for item in files if item.attachment_slot==key]} for key,label in FILE_SLOTS]

def save_slot_file(food,user,key,uploaded):
    from .models import Activity
    Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,dict(FILE_SLOTS)[key]),attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage='gate1',attachment_slot=key)

from .gate1_typed import Gate1Form

def initial_brief(food):
    from .models import Gate1Brief
    brief=Gate1Brief.objects.filter(food=food).first()
    return json.loads(brief.data) if brief else {}

def save_brief(food,data):
    from .models import Gate1Brief
    previous=initial_brief(food)
    payload=dict(data)
    payload['_schema_version']=2
    if previous.get('_schema_version') != 2: payload['_legacy_free_text']=previous
    elif previous.get('_legacy_free_text'): payload['_legacy_free_text']=previous['_legacy_free_text']
    Gate1Brief.objects.update_or_create(food=food,defaults={'data':json.dumps(payload,ensure_ascii=False,default=str)})
