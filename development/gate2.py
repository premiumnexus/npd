"""Gate 2 inputs; data types and business rules will be defined later."""
from django import forms
from django.db import transaction

FIELDS = [
    ('1.1','mass_trial_result','Масс туршилтын багц (кг)'),
    ('2.2','recipe_change_reason','Жор өөрчилсөн шалтгаан'),
    ('2.4','final_cogs_invoice_price','Эцсийн COGS'),
    ('2.5','cogs_limit','Gate 0 COGS хязгаар'),
    ('2.6','cogs_gap_percent','COGS зөрүү (%)'),
    ('2.6','cogs_status','COGS төлөв'),
    ('2.7','vendor_invoice_price','Нийлүүлэгчийн нэхэмжлэхийн үнэ (₮, НӨАТ-гүй)'),
    ('2.8','front_margin_percent','Бодит үнээрх CU ашгийн хувь (%)'),
    ('2.9','margin_gap_points','CU ашгийн зорилтоос дутсан зөрүү (нэгж хувь)'),
    ('2.10','implied_vendor_margin_percent','Бодит үнээрх нийлүүлэгчийн ашгийн хувь (%)'),
    ('2.11','invoice_price_status','Нэхэмжлэхийн үнийн төлөв'),
    ('2.12','overall_cost_status','Gate 2 өртгийн нийт төлөв'),
    ('3.1','lab_results_approved_shelf_life','Микробиологийн шинжилгээ (Тэнцсэн / Тэнцээгүй)'),
    ('3.2','chemical_lab_result','Химийн шинжилгээ'),
    ('3.3','approved_shelf_life_hours','Батлагдсан хадгалах хугацаа (цаг)'),
    ('1.9','final_technology_transfer_document','Технологи шилжүүлэх баримтын хувилбар'),
    ('4.1','label_allergens','Орцын жагсаалтад мэдэгдсэн харшил үүсгэгчид (MNS 6648:2016)'),
    ('4.2','nutrition_info','Шим тэжээлийн мэдээлэл (100 г тутамд)'),
    ('4.3','label_checked','Шошгыг шалгасан эсэх'),
    ('2.6','barcode_system_registration','Баркод, системийн бүртгэл'),
    ('2.7','allocation','Хуваарилалт'),
    ('2.8','supply_readiness','Нийлүүлэлтийн бэлэн байдал'),
    ('2.9','marketing_plan','Маркетингийн төлөвлөгөө'),
    ('1.5','quality_tolerance_baseline','Жингийн зорилт (г)'),
    ('2.11','day45_target_confirmed','45 хоногийн зорилт баталгаажуулах'),
    ('2.12','launch_date','Нэвтрүүлэх огноо'),
]

FILE_SLOTS = [
    ('G2-F1','Масс туршилтын бүртгэл (файл)'),
    ('G2-F2','Нийлүүлэгчийн эцсийн үнийн санал (файл)'),
    ('G2-F3','Лабораторийн тайлан (файл)'),
    ('G2-F4','Хадгалах хугацааны тайлан (файл)'),
    ('G2-F5','Технологи шилжүүлэх баримт, гарын үсэгтэй (файл)'),
    ('G2-F6','HACCP / CCP төлөвлөгөө (файл)'),
    ('G2-F7','Шошгоны эцсийн загвар (файл)'),
    ('G2-F8','Савлагааны эцсийн техникийн тодорхойлолт (файл)'),
    ('G2-F9','Маркетингийн төлөвлөгөө'),
    ('G2-F10','Хуваарилалтын төлөвлөгөө'),
    ('G2-F12','ISF Manual'),
    ('G2-F13','Чанарын стандарт (файл)'),
]

def available_file_slots(food):
    from .gate0 import initial_brief as gate0_brief
    isf=gate0_brief(food).get('category')=='ISF'
    return [(key,label) for key,label in FILE_SLOTS if key!='G2-F12' or isf]


def file_slots(food):
    files=list(food.gate2_files.select_related('uploader'))
    inline_files=list(food.activities.filter(attachment_stage='gate2',attachment_slot__in=['G2-F12','G2-F13']).select_related('actor').order_by('-created','-pk'))
    inline_numbers={'G2-F5':'1.11','G2-F1':'1.12','G2-F13':'1.13','G2-F2':'2.13','G2-F12':'2.12','G2-F3':'3.4','G2-F4':'3.5','G2-F6':'3.6','G2-F7':'4.4','G2-F8':'4.5'}
    return [{'key':key,'label':label,'number':inline_numbers.get(key,key),'inline':key in inline_numbers,'required':key in ('G2-F5','G2-F2','G2-F3','G2-F6','G2-F7','G2-F8'),'files':[item for item in inline_files if item.attachment_slot==key] if key in ('G2-F12','G2-F13') else [item for item in files if item.slot_code==key]} for key,label in available_file_slots(food)]

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
    if data.get('approved_shelf_life_hours') is None and isinstance(data.get('approved_shelf_life_days'),int):
        data['approved_shelf_life_hours']=data['approved_shelf_life_days']*24
    from .gate2_typed import derived_values
    data.update({key:serialize(value) for key,value in derived_values(food,None,data.get('launch_date'),data.get('vendor_invoice_price')).items()})
    return data


def save_brief(food,data):
    from .gate_storage import save_gate
    payload=dict(data)
    if food.recipe_version is not None: payload['final_recipe_version']=food.recipe_version
    return save_gate(2,food,payload)
