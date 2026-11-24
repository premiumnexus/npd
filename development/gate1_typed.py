from decimal import Decimal,InvalidOperation
from django import forms
from .models import PackagingType,COGSComparisonPolicy
from .gate0_rows import RowsField,AttachmentRow
from .cogs_widgets import COGSStatusWidget

class TrialRow(AttachmentRow):
    attachment_model='Gate1File'
    number=forms.IntegerField(label='№',min_value=1)
    date=forms.DateField(label='Огноо',widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    changes=forms.CharField(label='Юу өөрчилсөн',widget=forms.Textarea(attrs={'rows':2}))
    result=forms.CharField(label='Үр дүн',widget=forms.Textarea(attrs={'rows':2}))
    tasting_score=forms.DecimalField(label='Амталгааны үнэлгээ (1–5)',min_value=1,max_value=5,max_digits=4,decimal_places=2)
    cogs=forms.DecimalField(label='COGS (₮)',min_value=0,max_digits=14,decimal_places=2)
    decision=forms.ChoiceField(label='Шийдвэр',choices=[('','---------'),('continue','Үргэлжлүүлэх'),('approved','Батлагдсан'),('stop','Зогсоох')])
    lessons=forms.CharField(label='Сургамж',widget=forms.Textarea(attrs={'rows':2}))
    file=forms.FileField(label='Файл',required=False)
    attachment=forms.IntegerField(min_value=1,required=False,widget=forms.HiddenInput)

class MaterialRow(AttachmentRow):
    attachment_model='Gate1File'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .dropdown_options import apply_options
        apply_options(self, 'gate1', 'raw_material_spec_price_moq_second_source.')

    material=forms.CharField(label='Шинэ / өөрчлөгдсөн түүхий эд')
    spec_written=forms.ChoiceField(label='Техникийн тодорхойлолт бичигдсэн эсэх',choices=[('','---------'),('yes','Тийм'),('no','Үгүй')])
    price_kg=forms.DecimalField(label='Үнэ (₮ / кг)',min_value=0,max_digits=14,decimal_places=2)
    moq=forms.DecimalField(label='MOQ',min_value=0,max_digits=14,decimal_places=3)
    second_source=forms.ChoiceField(label='Нийлүүлэлтийн өөр эх үүсвэр байгаа эсэх',choices=[('','---------'),('yes','Тийм'),('no','Үгүй')])
    file=forms.FileField(label='Түүхий эдийн техникийн тодорхойлолт',required=False)
    attachment=forms.IntegerField(min_value=1,required=False,widget=forms.HiddenInput)

def cost_comparison(food,typed_cogs,packaging=None):
    from .gate0 import initial_brief
    def decimal(value):
        try:
            result=Decimal(str(value))
            return result if result.is_finite() else None
        except (ValueError,TypeError,InvalidOperation): return None
    typed=decimal(typed_cogs)
    pack=decimal(packaging) if packaging is not None else (food.packaging if food else Decimal(0))
    cogs=(food.ingredient_cost+pack if pack is not None else None) if food and food.lines.exists() else (typed if typed is not None else (pack if pack else None))
    limit=decimal(initial_brief(food).get('cogs_limit')) if food else None
    policy=COGSComparisonPolicy.objects.first()
    result={'estimated_cogs_vs_limit':cogs,'cogs_limit':limit,'cogs_status':'Хүлээгдэж байна','cogs_source':'Гараар оруулсан' if typed is not None else ('Орцын тооцоо' if cogs is not None else '')}
    band=policy.amber_band_percent if policy else Decimal('5')
    if food and food.lines.exists(): result['cogs_source']='Орцын тооцоо + савлагаа'
    result.update({'cogs_gap_percent':None,'amber_band':band,'send_to_director':''})
    if cogs is None or limit is None or limit<=0: return result
    gap=(cogs/limit-1)*100
    result['cogs_gap_percent']=gap
    result['cogs_status']='Green' if gap<=0 else ('Amber' if gap<=band else 'Red')
    result['send_to_director']='Yes' if result['cogs_status']=='Red' else 'No'

    return result

class Gate1Form(forms.Form):
    marketing_keys=('marketing_name','marketing_key_message','marketing_brief')
    recipe_keys=('trial_log','recipe_version_internal_tasting','typed_cogs','typed_cogs_reason','estimated_cogs_vs_limit','cogs_limit','cogs_gap_percent','cogs_status','amber_band','send_to_director','cogs_source','cogs_reason','cogs_action')
    tasting_keys=('taster_count','tasting_score','consumer_test','consumer_liking','consumer_would_buy_percent')
    material_keys=('raw_material_spec_price_moq_second_source',)
    production_keys=('capacity_equipment_fit','capacity_units_day','capacity_constraint','constraint_details')
    packaging_keys=('packaging_label_concept','packaging_unit_price','pack_material','pack_size','material_certificate','packaging_supplier','packaging_moq','packaging_lead_days')
    safety_keys=('qa_requirements_issued','process_flow_ccp_issued','fridge_check_72h','tested_in_actual_packaging','fridge_check_date','shelf_life_test_plan','shelf_life_test_days','shelf_life_result_due')

    @property
    def intro_fields(self): return [self[key] for key in ('trial_log','recipe_version_internal_tasting')]

    @property
    def manual_cost_fields(self): return [self[key] for key in ('typed_cogs','typed_cogs_reason','cogs_reason')]

    @property
    def tasting_fields(self): return [self[key] for key in self.tasting_keys]

    @property
    def material_fields(self): return [self[key] for key in self.material_keys]

    @property
    def production_fields(self): return [self[key] for key in self.production_keys]

    @property
    def packaging_fields(self): return [self[key] for key in self.packaging_keys]

    @property
    def safety_fields(self): return [self[key] for key in self.safety_keys]

    @property
    def gate0_shelf_life_hours(self):
        if not self.food: return None
        from .models import Gate0
        data=Gate0.objects.filter(development=self.food).values('shelf_life_hours','shelf_life_days').first()
        if not data: return None
        if data['shelf_life_hours'] is not None: return data['shelf_life_hours']
        return data['shelf_life_days']*24 if data['shelf_life_days'] is not None else None

    @property
    def legacy_material_files(self):
        return list(self.food.gate1_files.filter(slot_code='G1-F4',material_rows__isnull=True)) if self.food else []

    @property
    def marketing_fields(self): return [self[key] for key in self.marketing_keys]

    @property
    def other_fields(self): return [field for field in self if field.name not in self.recipe_keys+self.tasting_keys+self.material_keys+self.production_keys+self.packaging_keys+self.safety_keys+self.marketing_keys]

    def __init__(self,*args,food=None,submission=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.food=food
        self.submission=submission
        if not self.is_bound:
            self.initial=self.initial.copy()
            if food and self.initial.get('capacity_units_day') in (None,''):
                from .models import Gate0
                capacity=Gate0.objects.filter(development=food).values_list('capacity_units_day',flat=True).first()
                if capacity is not None: self.initial['capacity_units_day']=capacity
            legacy_constraints={'cooling':'Хөргөлт','packing':'Савлагаа','space':'Талбай','labour':'Хөдөлмөр','other':'Бусад'}
            previous=self.initial.get('capacity_constraint')
            if isinstance(previous,str) and previous in legacy_constraints:
                self.initial['capacity_constraint']='yes'
                self.initial['constraint_details']=': '.join(filter(None,[legacy_constraints[previous],self.initial.get('constraint_details')]))
        def add(key,label,number,field):
            field.required=False
            field.label=label
            field.gate_number=number
            field.help_text=number+' · '+str(field.help_text or '')
            self.fields[key]=field
        def text(): return forms.CharField(widget=forms.Textarea(attrs={'rows':2}))
        def num(minimum=0,maximum=None,places=2): return forms.DecimalField(min_value=minimum,max_value=maximum,max_digits=14,decimal_places=places)
        def enum(items): return forms.ChoiceField(choices=[('','---------')]+items)
        def date(): return forms.DateField(widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
        yesno=[('yes','Тийм'),('no','Үгүй')]
        add('trial_log','Туршилтын бүртгэл (мөр)','1.1',RowsField(TrialRow,required=False,complete=False))
        add('recipe_version_internal_tasting','Жорын хувилбарын дугаар','1.2',forms.IntegerField(min_value=1,help_text='Жорын хувилбарын бүртгэл байхгүй бол гараар оруулна.'))
        if food and food.recipe_version is not None:
            self.initial['recipe_version_internal_tasting']=food.recipe_version
            self.fields['recipe_version_internal_tasting'].disabled=True
        add('tasting_score','Дотоод амталгааны үнэлгээ (1–5)','2.2',num(1,5))
        add('taster_count','Амтлагчдын тоо (5-аас доошгүй)','2.1',forms.IntegerField(min_value=5))
        add('consumer_test','Туршилтад оролцсон хэрэглэгчдийн тоо','2.4',forms.IntegerField(min_value=1))
        add('consumer_liking','Таалагдсан үнэлгээ (1–9)','2.5',num(1,9))
        add('consumer_would_buy_percent','Зорилтот үнээр худалдан авах хувь (%)','2.6',num(0,100))
        add('typed_cogs','COGS гараар оруулах (₮)','1.10',num())
        add('typed_cogs_reason','COGS гараар оруулах шалтгаан','1.10',text())
        if food and food.lines.exists():
            self.fields['typed_cogs'].disabled=True
            self.fields['typed_cogs'].help_text='Жорын орц бүртгэлтэй тул COGS-ийг орц ба савлагаанаас тооцно.'
        for key,label in [('estimated_cogs_vs_limit','Тооцоолсон COGS (₮)'),('cogs_limit','Gate 0 COGS хязгаар (₮)'),('cogs_status','COGS төлөв'),('cogs_gap_percent','COGS зөрүү (%)'),('amber_band','Amber босго (%)'),('send_to_director','Merchandising Director руу шилжүүлэх эсэх'),('cogs_source','COGS эх үүсвэр')]:
            add(key,label,'1.3',forms.CharField(disabled=True))
            self.fields[key].widget.attrs['class']='costing-result'
        for key in ['amber_band','send_to_director']:
            self.fields[key].frontend_hidden=True
        self.fields['cogs_status'].widget=COGSStatusWidget(attrs={'class':'costing-result','data-recipe-status':True})
        self.fields['cogs_status'].help_text+=' Ногоон: хязгаараас ихгүй; Шар: зөвшөөрөх босго хүртэл; Улаан: босгоос их.'
        add('cogs_reason','Amber / Red шалтгаан','1.11',text())
        add('cogs_action','Amber / Red үед авах арга хэмжээ','1.12',text())
        for key,number in [('estimated_cogs_vs_limit','1.6'),('cogs_limit','1.7'),('cogs_gap_percent','1.8'),('cogs_status','1.9')]:
            self.fields[key].help_text=self.fields[key].help_text.replace(self.fields[key].gate_number+' · ',number+' · ',1)
            self.fields[key].gate_number=number
        add('raw_material_spec_price_moq_second_source','Шинэ эсвэл өөрчлөгдсөн түүхий эд','3.1',RowsField(MaterialRow,required=False,complete=False))
        add('capacity_equipment_fit','Үйлдвэрлэлийн шугам','4.1',text())
        add('capacity_units_day','Хүчин чадал (ширхэг/өдөр)','4.2',num())
        self.fields['capacity_units_day'].help_text+=' Gate 0 5.7-оос урьдчилан бөглөгдөнө. Шалгаж, хадгалж баталгаажуулна уу.'
        self.fields['capacity_units_day'].gate_capacity_confirmation=True
        add('capacity_constraint','Хязгаарлалт байгаа эсэх','4.3',enum(yesno))
        add('constraint_details','Хязгаарлалтын тайлбар','4.4',text())
        add('qa_requirements_issued','Хориглосон орцыг шалгасан эсэх','6.1',enum(yesno))
        add('process_flow_ccp_issued','Процессын урсгал ба CCP шаардлага гаргасан эсэх','6.2',enum(yesno))
        add('fridge_check_72h','Хадгалалтын шалгалтын үр дүн','6.3',enum([('pass','Тэнцсэн'),('fail','Тэнцээгүй')]))
        self.fields['fridge_check_72h'].gate_shelf_life_reference=True
        add('tested_in_actual_packaging','Бодит савлагаанд шалгасан эсэх','6.4',enum(yesno))
        add('fridge_check_date','Шалгасан огноо','6.5',date())
        add('shelf_life_test_plan','Лаборатори','6.7',text())
        add('shelf_life_test_days','Туршилтын хугацаа (хоног)','6.8',forms.IntegerField(min_value=1))
        add('shelf_life_result_due','Үр дүн гарах огноо','6.9',date())
        add('packaging_label_concept','Савлагаа (одоо байгаа эсвэл шинэ)','5.1',enum([(item.code,item.name) for item in PackagingType.objects.filter(active=True)]))
        add('packaging_unit_price','Нэгжийн үнэ (₮)','5.2',forms.DecimalField(min_value=0,max_digits=12,decimal_places=2))
        self.initial.setdefault('packaging_unit_price',food.packaging if food else Decimal(0))
        self.fields['packaging_unit_price'].widget.attrs['data-packaging-unit-price']=True
        from .models import Gate1
        for key,label,number in [('pack_material','Савлагааны материал','5.3'),('pack_size','Савлагааны хэмжээ','5.4')]:
            old=list(Gate1.objects.exclude(**{key+'__isnull':True}).exclude(**{key:''}).order_by(key).values_list(key,flat=True).distinct())
            if self.initial.get(key) and self.initial[key] not in old: old.append(self.initial[key])
            add(key,label,number,enum([(value,value) for value in old]))
        add('material_certificate','Хүнстэй харьцах материалын гэрчилгээ байгаа эсэх','5.5',enum(yesno))
        add('packaging_supplier','Шинэ савлагаа бол: нийлүүлэгч','5.6',text())
        add('packaging_moq','Шинэ савлагаа бол: MOQ','5.6',num(places=3))
        add('packaging_lead_days','Шинэ савлагаа бол: нийлүүлэх хугацаа (хоног)','5.6',forms.IntegerField(min_value=0))
        add('marketing_name','Кампанит ажлын нэр','7.1',text())
        add('marketing_key_message','Гол мессеж','7.2',text())
        add('marketing_brief','Нэвтрүүлэлтийн маркетингийн санаа','7.3',text())
        from .dropdown_options import apply_options
        apply_options(self, 'gate1')
        for key in self.safety_keys[:5]:
            self.fields[key].gate_required=True
            self.fields[key].required=submission
        for key in ('packaging_label_concept','material_certificate'):
            self.fields[key].gate_required=True
            self.fields[key].required=submission
        self.fields['capacity_constraint'].choices=[('','---------')]+yesno
        self.fields['capacity_constraint'].widget=forms.Select(choices=self.fields['capacity_constraint'].choices)
        constraint=self.data.get('capacity_constraint') if self.is_bound else self.initial.get('capacity_constraint')
        for key in self.production_keys:
            field=self.fields[key]
            field.gate_production_conditional=key=='constraint_details'
            field.gate_required=key!='constraint_details' or constraint=='yes'
            field.required=submission and field.gate_required
        consumer_count=self.data.get('consumer_test') if self.is_bound else self.initial.get('consumer_test')
        for key in ('taster_count','tasting_score','consumer_liking','consumer_would_buy_percent'):
            field=self.fields[key]
            conditional=key in ('consumer_liking','consumer_would_buy_percent')
            field.gate_conditional_required=conditional
            field.gate_required=not conditional or consumer_count not in (None,'')
            field.required=submission and field.gate_required
        self.legacy_values=[]
        if not self.is_bound:
            for key,field in self.fields.items():
                value=self.initial.get(key)
                if value in (None,'',[]): continue
                try:
                    if isinstance(field,RowsField) and not isinstance(value,list): raise ValueError()
                    field.clean(value)
                except (forms.ValidationError,ValueError,TypeError):
                    self.legacy_values.append((field.label,value))
                    self.initial[key]=[] if isinstance(field,RowsField) else ''
        raw=self.data.get('typed_cogs') if self.is_bound else self.initial.get('typed_cogs')
        price=self.data.get('packaging_unit_price') if self.is_bound else self.initial.get('packaging_unit_price')
        self.initial.update(cost_comparison(food,raw,packaging=price))

    def clean(self):
        data=super().clean()
        if 'packaging_unit_price' in self.data and 'packaging_unit_price' not in self.errors:
            data['packaging_unit_price']=data.get('packaging_unit_price') or Decimal(0)
        data.update(cost_comparison(self.food,data.get('typed_cogs'),packaging=data.get('packaging_unit_price')))
        from .models import Gate1File
        for key,slot in [('trial_log','G1-F1'),('raw_material_spec_price_moq_second_source','G1-F4')]:
            attachments={row['attachment'] for row in data.get(key,[]) if row.get('attachment')}
            allowed=set(Gate1File.objects.filter(development=self.food,slot_code=slot,pk__in=attachments).values_list('pk',flat=True)) if self.food else set()
            if attachments-allowed: self.add_error(key,'Хавсралт энэ бүтээгдэхүүний талбарт хамаарахгүй байна.')
        if self.submission:
            lines=list(self.food.lines.select_related('ingredient')) if self.food else []
            if not lines or any(line.quantity<=0 or line.ingredient.unit!='kg' or not Decimal('.01')<=line.yield_factor<=1 or line.unit_price<0 for line in lines):
                self.add_error(None,'1.4 Жорын орц заавал бүртгэнэ. Орц бүрийн цэвэр жин 0-ээс их, гарц 0.01–1.00 байна.')
        return data
