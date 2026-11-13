from datetime import timedelta
from decimal import Decimal, InvalidOperation
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
    from .models import GateAccess
    from .workflow import SCIENCE,PLANNING,QA
    if day not in [7,14] or food.stage!='launch' or food.completed or food.review_status!='draft': return False
    if not schedule(food,now)['day%s_open'%day]: return False
    if user.is_superuser: return True
    roles=[SCIENCE,PLANNING]+([QA] if day==14 else [])
    return GateAccess.objects.filter(group__user=user,group__name__in=roles,stage='launch',can_edit=True).exists()

REPORT_SLOTS={
    7:('L7F8','report','7 дахь өдрийн чанарын шалгалтын тайлан, зураг'),
    14:('L14F10','report','14 дэх өдрийн чанарын шалгалтын тайлан, зураг'),
}

def checkpoint_slots(day):
    return [REPORT_SLOTS[day]] if day in REPORT_SLOTS else []


def achievement(actual, target):
    def number(value):
        try:
            result=Decimal(str(value))
            return result if result.is_finite() and result>=0 else None
        except (InvalidOperation,ValueError,TypeError): return None
    actual,target=number(actual),number(target)
    percent=actual/target*100 if actual is not None and target is not None and target>0 else None
    status='Pending' if percent is None else 'Green' if percent>=100 else 'Amber' if percent>=80 else 'Red'
    return {'percent':percent.quantize(Decimal('.01')) if percent is not None else None,'status':status}

class CheckpointForm(forms.Form):
    def __init__(self,*args,day,food=None,user=None,now=None,**kwargs):
        from .models import LaunchCheckpoint,GateAccess
        from .gate2 import initial_brief,Gate2Form
        from .workflow import SCIENCE,PLANNING,QA
        if day not in [7,14]: raise ValueError('Only Day 7 and Day 14 checkpoints accept entries.')
        kwargs.setdefault('auto_id','id_day%s_%%s'%day)
        saved=LaunchCheckpoint.objects.filter(food=food,day=day).first() if food else None
        initial={
            'checked_date':saved.checked_date if saved else None,
            'sample_result':(saved.sample_result or {'yes':'within','no':'outside'}.get(saved.within_tolerance,'')) if saved else '',
            'actual_apsd':saved.sales_snapshot if saved else None,
            'action_plan':saved.action_plan if saved else '',
            'complaints_count':saved.complaints_count if saved else None,
        }
        initial.update(kwargs.pop('initial',{}))
        baseline=initial_brief(food) if food else {}
        initial['target_apsd']=Gate2Form(initial=baseline,food=food).initial.get('day45_units_store_day') if food else None
        self.achievement=achievement(initial['actual_apsd'],initial['target_apsd'])
        initial['achievement_percent']=self.achievement['percent']
        kwargs['initial']=initial
        super().__init__(*args,**kwargs)
        self.day=day
        self.food=food
        editable=bool(user and food and can_edit_checkpoint(user,food,day,now))
        science=editable and (user.is_superuser or GateAccess.objects.filter(group__user=user,group__name=SCIENCE,stage='launch',can_edit=True).exists())
        planning=editable and (user.is_superuser or GateAccess.objects.filter(group__user=user,group__name=PLANNING,stage='launch',can_edit=True).exists())
        qa=editable and (user.is_superuser or GateAccess.objects.filter(group__user=user,group__name=QA,stage='launch',can_edit=True).exists())
        self.fields['checked_date']=forms.DateField(label='Шалгасан огноо',required=False,disabled=not science,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
        self.fields['sample_result']=forms.ChoiceField(label='Дээжийн үр дүн',required=False,disabled=not science,choices=[('','---------'),('within','Хязгаарт багтсан'),('conditional','Нөхцөлтэй'),('outside','Хязгаараас гарсан')])
        self.fields['actual_apsd']=forms.DecimalField(label='Бодит APSD',required=False,disabled=not planning,min_value=0,max_digits=14,decimal_places=2)
        self.fields['target_apsd']=forms.DecimalField(label='Зорилтот APSD',required=False,disabled=True,min_value=0,max_digits=14,decimal_places=2,widget=forms.NumberInput(attrs={'class':'costing-result'}))
        self.fields['achievement_percent']=forms.DecimalField(label='Зорилтын биелэлт %',required=False,disabled=True,max_digits=22,decimal_places=2)
        if day==14:
            self.fields['complaints_count']=forms.IntegerField(label='Гомдлын тоо',required=False,disabled=not qa,min_value=0,max_value=2147483647)
            self.fields['complaints_count'].responsible_role='QA'
        self.fields['action_plan']=forms.CharField(label='Арга хэмжээ, хариуцагч, хугацаа',required=False,disabled=not editable,widget=forms.Textarea(attrs={'rows':3}))
        for key in ['checked_date','sample_result']: self.fields[key].responsible_role='Хүнсний технологич'
        self.fields['actual_apsd'].responsible_role='FF төлөвлөлт'
        result=self.data.get('sample_result') if self.is_bound and science else self.initial['sample_result']
        self.action_required=result in ['conditional','outside']
        self.fields['action_plan'].required=self.action_required
        for slot,key,label in checkpoint_slots(day):
            self.fields[key]=forms.FileField(label=label,required=False,disabled=not editable)

    def clean(self):
        data=super().clean()
        self.action_required=data.get('sample_result') in ['conditional','outside']
        if not self.action_required: data['action_plan']=''
        self.achievement=achievement(data.get('actual_apsd'),self.initial['target_apsd'])
        data['target_apsd']=self.initial['target_apsd']
        data['achievement_percent']=self.achievement['percent']
        return data


def save_checkpoint(food,user,form):
    from .models import LaunchCheckpoint,Activity
    data=form.cleaned_data
    result=data.get('sample_result','')
    values={
        'checked_date':data.get('checked_date'), 'sample_result':result,
        'sales_snapshot':data.get('actual_apsd'), 'action_plan':data.get('action_plan',''),
        'within_tolerance':'yes' if result=='within' else 'no' if result else '',
        'actor':user,'recorded_at':timezone.now(),
    }
    if form.day==14: values['complaints_count']=data.get('complaints_count')
    LaunchCheckpoint.objects.update_or_create(food=food,day=form.day,defaults=values)
    Activity.objects.create(food=food,actor=user,text='Launch GO / Day %s / Шалгалтын мэдээлэл хадгалав' % form.day)

def checkpoint_cards(user,food,now=None):
    from .gate2 import initial_brief
    dates=schedule(food,now)
    baseline=initial_brief(food)
    uploads=list(food.activities.filter(attachment_stage='launch').exclude(attachment=''))
    cards=[]
    for day in [7,14]:
        editable=can_edit_checkpoint(user,food,day,now)
        form=CheckpointForm(day=day,food=food,user=user,now=now)
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
