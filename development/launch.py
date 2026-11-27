from decimal import Decimal, InvalidOperation
from django import forms
from django.utils import timezone
from .gate0_rows import RowsField


class LaunchActionRow(forms.Form):
    what=forms.CharField(label='Юу',widget=forms.Textarea(attrs={'rows':2}))
    who=forms.CharField(label='Хэн',max_length=200)
    when=forms.DateField(label='Хэзээ',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))


class LaunchDecisionForm(forms.Form):
    def __init__(self,*args,food,**kwargs):
        from .models import LaunchDecision
        self.food=food
        record=LaunchDecision.objects.filter(development=food).first()
        initial={'decision':record.decision if record else '',
                 'decision_actions':list(record.actions.values('what','who','when')) if record else []}
        initial.update(kwargs.pop('initial',{}))
        kwargs.setdefault('auto_id','id_launch_%s')
        super().__init__(*args,initial=initial,**kwargs)
        self.fields['decision']=forms.ChoiceField(label='Шийдвэр',choices=[('','---------'),('continue','Үргэлжлүүлэх'),('fix','Засах'),('stop','Зогсоох')])
        self.fields['decision'].gate_number='3.1'
        self.fields['decision'].gate_required=True
        self.fields['decision_actions']=RowsField(LaunchActionRow,complete=True,required=False,label='Арга хэмжээ (мөр): юу · хэн · хэзээ')
        self.fields['decision_actions'].gate_number='3.2'


def save_launch_decision(food,user,form):
    from .models import LaunchDecision,LaunchAction,Activity
    record,_=LaunchDecision.objects.update_or_create(development=food,defaults={'decision':form.cleaned_data['decision']})
    record.actions.all().delete()
    LaunchAction.objects.bulk_create([LaunchAction(decision=record,position=position,**row)
                                     for position,row in enumerate(form.cleaned_data['decision_actions'])])
    Activity.objects.create(food=food,actor=user,text='Launch GO / Шийдвэр: '+record.get_decision_display())


def validate_launch_decision(food):
    form=LaunchDecisionForm(food=food)
    data={'decision':form.initial['decision'],'decision_actions':form.initial['decision_actions']}
    return LaunchDecisionForm(data,food=food)

def can_edit_checkpoint(user,food,day,now=None):
    from .models import GateAccess
    from .workflow import SCIENCE,PLANNING,QA
    if day not in [7,14] or food.stage!='launch' or food.completed or food.review_status!='draft': return False
    if user.is_superuser: return True
    roles=[SCIENCE,PLANNING,QA]
    return GateAccess.objects.filter(group__user=user,group__name__in=roles,stage='launch',can_edit=True).exists()

REPORT_SLOTS={
    7:('L7F8','report','Чанарын шалгалтын тайлан, зураг (файл)'),
    14:('L14F10','report','Чанарын шалгалтын тайлан, зураг (файл)'),
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


def writeoff_status(actual,target):
    try:
        actual,target=Decimal(str(actual)),Decimal(str(target))
        if not actual.is_finite() or not target.is_finite(): return 'Pending'
    except (InvalidOperation,ValueError,TypeError): return 'Pending'
    return 'Green' if actual<=target else 'Red'

class CheckpointForm(forms.Form):
    def __init__(self,*args,day,food=None,user=None,now=None,submission=False,**kwargs):
        from .models import LaunchCheckpoint,GateAccess
        from .gate2 import initial_brief,Gate2Form
        from .workflow import SCIENCE,PLANNING,QA
        if day not in [7,14]: raise ValueError('Only Day 7 and Day 14 checkpoints accept entries.')
        kwargs.setdefault('auto_id','id_day%s_%%s'%day)
        saved=LaunchCheckpoint.objects.filter(development=food,day=day).first() if food else None
        initial={
            'checked_date':saved.checked_date if saved else None,
            'sample_result':(saved.sample_result or {'yes':'within','no':'outside'}.get(saved.within_tolerance,'')) if saved else '',
            'actual_apsd':saved.sales_snapshot if saved else None,
            'action_plan':saved.action_plan if saved else '',
            'complaints_count':saved.complaints_count if saved else None,
            'sample_weight_g':saved.sample_weight_g if saved else None,
            'actual_writeoff_percent':saved.actual_writeoff_percent if saved else None,
            'promotion_period':saved.promotion_period if saved else '',
        }
        initial.update(kwargs.pop('initial',{}))
        baseline=initial_brief(food) if food else {}
        targets=Gate2Form(initial=baseline,food=food).initial if food else {}
        initial['target_apsd']=targets.get('day45_units_store_day')
        self.writeoff_target=targets.get('day45_writeoff_percent')
        self.writeoff_status=writeoff_status(initial['actual_writeoff_percent'],self.writeoff_target)
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
        self.fields['sample_weight_g']=forms.DecimalField(label='Дээжийн жин (г)',required=False,disabled=not science,min_value=0,max_digits=14,decimal_places=3)
        self.fields['sample_result']=forms.ChoiceField(label='Дээжийн үр дүн',required=False,disabled=not science,choices=[('','---------'),('within','Хязгаарт багтсан'),('conditional','Нөхцөлтэй'),('outside','Хязгаараас гарсан')])
        self.fields['actual_apsd']=forms.DecimalField(label='Бодит APSD',required=False,disabled=not planning,min_value=0,max_digits=14,decimal_places=2)
        self.fields['target_apsd']=forms.DecimalField(label='Зорилтот APSD',required=False,disabled=True,min_value=0,max_digits=14,decimal_places=2,widget=forms.NumberInput(attrs={'class':'costing-result'}))
        self.fields['achievement_percent']=forms.DecimalField(label='Зорилтын биелэлт %',required=False,disabled=True,max_digits=22,decimal_places=2)
        if day in (7,14):
            self.fields['complaints_count']=forms.IntegerField(label='Гомдлын тоо',required=False,disabled=not qa,min_value=0,max_value=2147483647)
            self.fields['complaints_count'].responsible_role='QA'
        self.fields['action_plan']=forms.CharField(label='Арга хэмжээ, хариуцагч, хугацаа',required=False,disabled=not editable,widget=forms.Textarea(attrs={'rows':3}))
        for key in ['checked_date','sample_result']: self.fields[key].responsible_role='Хүнсний технологич'
        self.fields['actual_apsd'].responsible_role='FF төлөвлөлт'
        result=self.data.get('sample_result') if self.is_bound and science and not submission else self.initial['sample_result']
        self.action_visible=result in ['conditional','outside']
        self.action_required=result=='outside'
        self.fields['action_plan'].required=self.action_required and (editable or submission)
        for slot,key,label in checkpoint_slots(day):
            self.fields[key]=forms.FileField(label=label,required=False,disabled=not editable)
        self.fields['sample_result'].choices=[('','---------'),('within','Тэнцсэн'),('conditional','Засвартай'),('outside','Тэнцээгүй')]
        self.fields['sample_result'].label='Дээжийн үр дүн (Тэнцсэн / Засвартай / Тэнцээгүй)'
        self.fields['action_plan'].label='Засвартай / Тэнцээгүй бол шалтгаан ба арга хэмжээ'
        self.fields['actual_writeoff_percent']=forms.DecimalField(label='Бодит акт % ба төлөв',required=False,disabled=not planning,min_value=0,max_value=100,max_digits=5,decimal_places=2)
        self.fields['promotion_period']=forms.ChoiceField(label='Урамшуулалтай хугацаа эсэх',required=False,disabled=not planning,choices=[('','---------'),('yes','Тийм'),('no','Үгүй')])
        keys=['checked_date','sample_weight_g','sample_result','action_plan','actual_apsd','target_apsd','achievement_percent','actual_writeoff_percent','complaints_count','promotion_period','report']
        self.order_fields(keys)
        for index,key in enumerate(keys,1): self.fields[key].gate_number='%s.%s'%(1 if day==7 else 2,index)
        for key in ('checked_date','sample_weight_g','sample_result','complaints_count'):
            self.fields[key].gate_required=True
            self.fields[key].required=submission or not self.fields[key].disabled
        self.fields['sample_weight_g'].responsible_role='Хүнсний технологич'
        for key in ('actual_writeoff_percent','promotion_period'): self.fields[key].responsible_role='FF төлөвлөлт'
        if submission:
            for field in self.fields.values(): field.disabled=True

    def clean(self):
        data=super().clean()
        self.action_visible=data.get('sample_result') in ['conditional','outside']
        self.action_required=data.get('sample_result')=='outside'
        if not self.action_visible: data['action_plan']=''
        self.achievement=achievement(data.get('actual_apsd'),self.initial['target_apsd'])
        data['target_apsd']=self.initial['target_apsd']
        data['achievement_percent']=self.achievement['percent']
        self.writeoff_status=writeoff_status(data.get('actual_writeoff_percent'),self.writeoff_target)
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
    values['complaints_count']=data.get('complaints_count')
    for key in ('sample_weight_g','actual_writeoff_percent','promotion_period'): values[key]=data.get(key)
    LaunchCheckpoint.objects.update_or_create(development=food,day=form.day,defaults=values)
    Activity.objects.create(food=food,actor=user,text='Launch GO / Day %s / Шалгалтын мэдээлэл хадгалав' % form.day)

def checkpoint_cards(user,food,now=None):
    from .gate2 import initial_brief
    baseline=initial_brief(food)
    uploads=list(food.activities.filter(attachment_stage='launch').exclude(attachment=''))
    standards=list(food.activities.filter(attachment_stage='gate2',attachment_slot='G2-F13').exclude(attachment=''))
    cards=[]
    for day in [7,14]:
        editable=can_edit_checkpoint(user,food,day,now)
        form=CheckpointForm(day=day,food=food,user=user,now=now)
        fields=[{'field':form[key], 'files':[item for item in uploads if item.attachment_slot==slot]}
                for slot,key,label in checkpoint_slots(day)]
        cards.append({'day':day,'editable':editable,'form':form,'upload_fields':fields,'baseline':baseline,'quality_standards':standards})
    return cards
