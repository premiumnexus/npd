from datetime import date
from decimal import Decimal,InvalidOperation
from django import forms

ROOT_CAUSES=[('demand','Эрэлт'),('price','Үнэ'),('quality','Чанар'),('availability','Бэлэн байдал'),('placement','Байршил'),('none','Байхгүй')]
LESSON_TAGS=[('ingredient','Орц'),('format','Формат'),('vendor','Нийлүүлэгч'),('issue','Асуудал')]

def derived_values(food,data):
    from .gate0 import initial_brief as gate0_data
    from .gate2 import initial_brief as gate2_data
    from .gate2_typed import derived_values as gate2_calcs
    original=gate0_data(food) if food else {}
    launch=gate2_data(food) if food else {}
    def decimal(value):
        try:
            value=Decimal(str(value))
            return value if value.is_finite() else None
        except (InvalidOperation,ValueError,TypeError): return None
    def date_value(value):
        try: return value if isinstance(value,date) else date.fromisoformat(str(value))
        except (ValueError,TypeError): return None
    planned=date_value(original.get('planned_launch_date'))
    actual=date_value(launch.get('launch_date'))
    late=max(0,(actual-planned).days) if planned and actual else None
    result={
        'planned_vs_actual_launch_date':str(planned) if planned else '',
        'actual_launch_date':str(actual) if actual else '',
        'launch_days_late':late,
    }
    for actual_key,target_key,output in [
        ('sales_vs_target','target_units_store_day','sales'),
        ('margin_after_writeoff','day45_margin_percent','margin'),
        ('writeoff_percent_of_cost','day45_writeoff_percent','writeoff'),
    ]:
        observed=decimal(data.get(actual_key))
        target=decimal(original.get(target_key))
        result[output+'_target']=target
        result[output+'_difference']=(observed-target).quantize(Decimal('0.01')) if observed is not None and target is not None else None
        if output=='sales': result['sales_attainment_percent']=(observed/target*100).quantize(Decimal('0.01')) if observed is not None and target is not None and target>0 else None
    checkpoints={item.day:item.within_tolerance for item in food.launch_checkpoints.all()} if food else {}
    result['shelf_samples_day7_day14']=checkpoints.get(7,'')
    result['day14_sample_within_tolerance']=checkpoints.get(14,'')
    slots=set(food.activities.exclude(attachment='').values_list('attachment_slot',flat=True)) if food else set()
    has_cogs=gate2_calcs(food,launch.get('typed_cogs'),launch.get('launch_date'))['final_cogs_invoice_price'] is not None if food else False
    flags={
        'handover_final_cogs':has_cogs or 'G2-F11' in slots,
        'handover_technology_document':bool(launch.get('final_technology_transfer_document')) or 'G2-F5' in slots,
        'handover_label':launch.get('label_checked')=='yes' or bool(launch.get('label_check')) or 'G2-F7' in slots,
        'handover_marketing_plan':bool(launch.get('marketing_plan')) or 'G2-F9' in slots,
    }
    result.update({key:'yes' if value else 'no' for key,value in flags.items()})
    result['handover_pack_complete']='yes' if all(flags.values()) else 'no'
    return result

class Gate3Form(forms.Form):
    def __init__(self,*args,food=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.food=food
        def add(key,label,number,field):
            field.required=False
            field.label=label
            field.gate_number=number
            field.help_text=number+' · '+str(field.help_text or '')
            self.fields[key]=field
        def text(): return forms.CharField(widget=forms.Textarea(attrs={'rows':2}))
        def number(minimum=0,maximum=None): return forms.DecimalField(min_value=minimum,max_value=maximum,max_digits=14,decimal_places=2)
        def enum(items,disabled=False): return forms.ChoiceField(choices=[('','---------')]+items,disabled=disabled)
        def readonly(): return forms.CharField(disabled=True)
        yesno=[('yes','Тийм'),('no','Үгүй')]
        add('planned_vs_actual_launch_date','Gate 0 (0.22) төлөвлөсөн огноо','3.1',readonly())
        add('actual_launch_date','Gate 2 (2.12) нэвтрүүлсэн огноо','3.1',readonly())
        add('launch_days_late','Хоцорсон хоног','3.1',readonly())
        add('launch_delay_reason','Нэвтрүүлэлт хоцорсон шалтгаан','3.1',text())
        self.fields['launch_delay_reason'].help_text+=' 7-оос олон хоног хоцорсон бол тайлбар оруулахыг зөвлөж байна. Талбар заавал биш.'
        add('sales_vs_target','45 хоногийн борлуулалт (ширхэг / дэлгүүр / өдөр)','3.2',number())
        add('sales_target','Gate 0 (0.14) борлуулалтын зорилт','3.2',readonly())
        add('sales_difference','Борлуулалтын зөрүү (бодит − зорилт)','3.2',readonly())
        add('sales_attainment_percent','Борлуулалтын зорилтын биелэлт (%)','3.2',readonly())
        add('margin_after_writeoff','Акт-ын дараах ашиг (%)','3.3',number(None,100))
        add('margin_target','Gate 0 (0.21) ашгийн зорилт (%)','3.3',readonly())
        add('margin_difference','Ашгийн зөрүү (хувийн пункт)','3.3',readonly())
        add('writeoff_percent_of_cost','акт (өртгийн %)','3.4',number(0,100))
        add('writeoff_target','Gate 0 (0.21) акт зорилт (%)','3.4',readonly())
        add('writeoff_difference','акт зөрүү (хувийн пункт)','3.4',readonly())
        add('availability','Бараагүй байсан дэлгүүр-хоног (%)','3.5',number(0,100))
        self.fields['availability'].help_text+=' Энэ нь бараа тасарсан дэлгүүр-хоногийн хувь юм.'
        add('shelf_samples_day7_day14','Day 7 дээж зөвшөөрөх хүрээнд эсэх','3.6',enum(yesno,True))
        add('day14_sample_within_tolerance','Day 14 дээж зөвшөөрөх хүрээнд эсэх','3.6',enum(yesno,True))
        self.fields['shelf_samples_day7_day14'].help_text+=' Launch GO хяналтын цэгээс автоматаар авна.'
        self.fields['day14_sample_within_tolerance'].help_text+=' Launch GO хяналтын цэгээс автоматаар авна.'
        add('complaints','Гомдлын тоо','3.7',forms.IntegerField(min_value=0))
        add('complaint_type','Гомдлын төрөл','3.7',text())
        add('complaints_closed','Гомдлыг хаасан эсэх','3.7',enum(yesno))
        add('customer_feedback','CSAT үнэлгээ','3.8',number())
        self.fields['customer_feedback'].help_text+=' CSAT хэмжүүрийн дээд хязгаар тодорхой болоогүй тул автоматаар хувьд хөрвүүлэхгүй.'
        add('customer_comments','Хэрэглэгчийн гол санал','3.8',text())
        add('root_cause','Шалтгааны онош','3.9',enum(ROOT_CAUSES))
        add('root_cause_evidence','Шалтгааны нотолгоо','3.9',text())
        add('lesson_card','Үргэлжлүүлэх зүйл','3.10',text())
        add('lesson_stop','Зогсоох зүйл','3.10',text())
        add('lesson_change','Өөрчлөх зүйл','3.10',text())
        add('lesson_tags','Сургамжийн шошго','3.10',forms.MultipleChoiceField(choices=LESSON_TAGS,widget=forms.CheckboxSelectMultiple))
        for key,label in [('handover_final_cogs','Эцсийн COGS байгаа эсэх'),('handover_technology_document','Технологи шилжүүлэх баримт байгаа эсэх'),('handover_label','Шошго байгаа эсэх'),('handover_marketing_plan','Маркетингийн төлөвлөгөө байгаа эсэх'),('handover_pack_complete','Handover багц бүрэн эсэх')]:
            add(key,label,'3.11',enum(yesno,True))
        from .dropdown_options import apply_options
        apply_options(self, 'gate3')
        self.legacy_values=[]
        if not self.is_bound:
            for key,field in self.fields.items():
                value=self.initial.get(key)
                if value in (None,'',[]): continue
                try: field.clean(value)
                except (forms.ValidationError,ValueError,TypeError):
                    self.legacy_values.append((field.label,value))
                    self.initial[key]=[] if isinstance(field,forms.MultipleChoiceField) else ''
        self.initial.update(derived_values(food,self.data if self.is_bound else self.initial))

    def clean(self):
        data=super().clean()
        data.update(derived_values(self.food,data))
        return data

    @property
    def delay_reason_recommended(self):
        values=getattr(self,'cleaned_data',{})
        return (values.get('launch_days_late') or 0)>7 and not values.get('launch_delay_reason')

