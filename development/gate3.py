"""Gate 3 review fields; types and business rules will be defined later."""
from django import forms

FIELDS = [
    ('3.1','planned_vs_actual_launch_date','Нэвтрүүлсэн огноо: төлөвлөгөө vs бодит'),
    ('3.2','sales_vs_target','Борлуулалт vs зорилт'),
    ('3.3','margin_after_writeoff','акт-ын дараах ашиг'),
    ('3.4','writeoff_percent_of_cost','акт, өртгийн %'),
    ('3.5','availability','Бэлэн байдал'),
    ('3.6','shelf_samples_day7_day14','Day 7, 14 тавиурын дээж'),
    ('3.7','complaints','Гомдол'),
    ('3.8','customer_feedback','Хэрэглэгчийн санал'),
    ('3.9','root_cause','Шалтгааны онош'),
    ('3.10','lesson_card','Сургамжийн карт'),
    ('3.11','handover_pack_complete','Handover багц бүрэн'),
]

FILE_SLOTS = [
    ('G3-F1','45 хоногийн борлуулалт, акт extract'),
    ('G3-F2','Day 7, 14 дээжийн бүртгэл'),
    ('G3-F3','Гомдлын бүртгэл'),
]

def file_slots(food):
    files=list(food.activities.filter(attachment_stage='gate3').exclude(attachment_slot=''))
    return [{'key':key,'label':label,'files':[item for item in files if item.attachment_slot==key]} for key,label in FILE_SLOTS]

def save_slot_file(food,user,key,uploaded):
    from .models import Activity
    Activity.objects.create(food=food,actor=user,text='%s · %s' % (key,dict(FILE_SLOTS)[key]),attachment=uploaded,attachment_name=uploaded.name[:255],attachment_stage='gate3',attachment_slot=key)

from .gate3_typed import Gate3Form

def initial_brief(food):
    from .gate_storage import read_gate, serialize
    data=read_gate(3,food)
    from .gate3_typed import derived_values
    data.update({key:serialize(value) for key,value in derived_values(food,data).items()})
    return data


def save_brief(food,data):
    from .gate_storage import save_gate
    return save_gate(3,food,data)
