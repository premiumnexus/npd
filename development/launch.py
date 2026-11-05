from datetime import timedelta
from django import forms
from django.utils import timezone

def schedule(food,now=None):
    now=now or timezone.now()
    start=food.launched_at
    values={'started_at':start,'day7_at':None,'day14_at':None,'day45_at':None,'day7_open':False,'day14_open':False,'gate3_open':False}
    if start:
        for day in [7,14,45]:
            due=start+timedelta(days=day)
            values['day%s_at'%day]=due
            values['gate3_open' if day==45 else 'day%s_open'%day]=now>=due
    return values

def can_edit_checkpoint(user,food,day,now=None):
    from .workflow import GateAccessQuery,SCIENCE,PLANNING,QA
    if day not in [7,14] or food.stage!='launch' or food.completed or food.review_status!='draft': return False
    if not schedule(food,now)['day%s_open'%day]: return False
    if user.is_superuser: return True
    roles=[SCIENCE,PLANNING]+([QA] if day==14 else [])
    return user.groups.filter(name__in=roles).exists() and GateAccessQuery(user,'launch','can_edit')

CHECKPOINT_FIELDS = [
    ('sample_weight', 'Дээжийн жин'),
    ('sample_texture', 'Дээжийн бүтэц'),
    ('sample_taste', 'Дээжийн амт'),
    ('sample_notes', 'Дээжийн тэмдэглэл'),
    ('sales_snapshot', 'Борлуулалтын үзүүлэлт'),
    ('sales_notes', 'Борлуулалтын тойм'),
    ('within_tolerance', 'Gate 2 (2.10) шалгууртай харьцуулсан дүгнэлт'),
    ('complaints_count', 'Гомдлын тоо'),
    ('complaints_details', 'Гомдлын мэдээлэл'),
]

def checkpoint_slots(day):
    return [('L%sF%s' % (day,index), key, label)
            for index,(key,label) in enumerate(CHECKPOINT_FIELDS,1)
            if day==14 or not key.startswith('complaints_')]

class CheckpointForm(forms.Form):
    def __init__(self,*args,day,**kwargs):
        kwargs.setdefault('auto_id','id_day%s_%%s'%day)
        super().__init__(*args,**kwargs)
        self.day=day
        for slot,key,label in checkpoint_slots(day):
            self.fields[key]=forms.FileField(label=label,required=False)

def checkpoint_cards(user,food,now=None):
    from .gate2 import initial_brief
    dates=schedule(food,now)
    baseline=initial_brief(food)
    uploads=list(food.activities.filter(attachment_stage='launch').exclude(attachment=''))
    cards=[]
    for day in [7,14]:
        editable=can_edit_checkpoint(user,food,day,now)
        form=CheckpointForm(day=day)
        for field in form.fields.values(): field.disabled=not editable
        fields=[{'field':form[key], 'files':[item for item in uploads if item.attachment_slot==slot]}
                for slot,key,label in checkpoint_slots(day)]
        cards.append({'day':day,'editable':editable,'due':dates['day%s_at'%day],
                      'unlocked':dates['day%s_open'%day],'form':form,'upload_fields':fields,'baseline':baseline})
    return cards

def open_gate3_if_due(food,now=None):
    """Caller locks the Food row. The rule becomes effective at Day 45."""
    from .models import Activity
    from .timing import record_transition
    now=now or timezone.now()
    dates=schedule(food,now)
    if food.stage!='launch' or food.completed or food.gate3_opened_at or not dates['gate3_open']: return False
    last_entry=food.gate_transitions.filter(to_stage='launch').exclude(from_stage='launch').order_by('-occurred_at','-pk').first()
    effective=max(dates['day45_at'],last_entry.occurred_at) if last_entry else dates['day45_at']
    previous=food.review_status
    food.stage='gate3'
    food.review_status='draft'
    food.gate3_opened_at=effective
    food.save(update_fields=['stage','review_status','gate3_opened_at','updated'])
    activity=Activity.objects.create(food=food,actor=None,text='Нэвтрүүлснээс хойш 45 хоног болсон тул Gate 3 автоматаар нээгдэв.')
    event=record_transition(food,None,'auto_open','launch',previous,activity)
    event.occurred_at=effective
    event.save(update_fields=['occurred_at'])
    return True

def open_due_reviews(now=None):
    from django.db import transaction
    from .models import Food
    now=now or timezone.now()
    count=0
    keys=Food.objects.filter(stage='launch',completed=False,gate3_opened_at__isnull=True,launched_at__lte=now-timedelta(days=45)).values_list('pk',flat=True)
    for pk in keys.iterator():
        with transaction.atomic():
            food=Food.objects.select_for_update().get(pk=pk)
            count+=int(open_gate3_if_due(food,now))
    return count
