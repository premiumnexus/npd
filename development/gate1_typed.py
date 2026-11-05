from decimal import Decimal,InvalidOperation
from django import forms
from .models import PackagingType,COGSComparisonPolicy
from .gate0_rows import RowsField

class MaterialRow(forms.Form):
    material=forms.CharField(label='Шинэ / өөрчлөгдсөн түүхий эд')
    spec_written=forms.ChoiceField(label='Спец бичигдсэн эсэх',choices=[('','---------'),('yes','Тийм'),('no','Үгүй')])
    price_kg=forms.DecimalField(label='Үнэ (₮ / кг)',min_value=0,max_digits=14,decimal_places=2)
    moq=forms.DecimalField(label='MOQ',min_value=0,max_digits=14,decimal_places=3)
    second_source=forms.ChoiceField(label='2 дахь эх үүсвэр байгаа эсэх',choices=[('','---------'),('yes','Тийм'),('no','Үгүй')])

def cost_comparison(food,typed_cogs):
    from .gate0 import initial_brief
    def decimal(value):
        try:
            result=Decimal(str(value))
            return result if result.is_finite() else None
        except (ValueError,TypeError,InvalidOperation): return None
    typed=decimal(typed_cogs)
    cogs=typed if typed is not None else (food.unit_cost if food and food.lines.exists() else None)
    limit=decimal(initial_brief(food).get('cogs_limit')) if food else None
    policy=COGSComparisonPolicy.objects.first()
    result={'estimated_cogs_vs_limit':cogs,'cogs_limit':limit,'cogs_status':'Хүлээгдэж байна','cogs_source':'Гараар оруулсан' if typed is not None else ('Орцын тооцоо' if cogs is not None else '')}
    if cogs is None or limit is None or limit<=0 or not policy or policy.green_max_percent is None or policy.amber_max_percent is None or policy.green_max_percent>policy.amber_max_percent: return result
    ratio=cogs/limit*100
    result['cogs_status']='Green' if ratio<=policy.green_max_percent else ('Amber' if ratio<=policy.amber_max_percent else 'Red')
    return result

class Gate1Form(forms.Form):
    def __init__(self,*args,food=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.food=food
        def add(key,label,number,field):
            field.required=False
            field.label=label
            field.help_text=number+' · '+str(field.help_text or '')
            self.fields[key]=field
        def text(): return forms.CharField(widget=forms.Textarea(attrs={'rows':2}))
        def num(minimum=0,maximum=None,places=2): return forms.DecimalField(min_value=minimum,max_value=maximum,max_digits=14,decimal_places=places)
        def enum(items): return forms.ChoiceField(choices=[('','---------')]+items)
        def date(): return forms.DateField(widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
        yesno=[('yes','Тийм'),('no','Үгүй')]
        add('recipe_version_internal_tasting','Жорын хувилбарын дугаар','1.1',forms.IntegerField(min_value=1,help_text='Жорын хувилбарын бүртгэл байхгүй бол гараар оруулна.'))
        if food and food.recipe_version is not None:
            self.initial['recipe_version_internal_tasting']=food.recipe_version
            self.fields['recipe_version_internal_tasting'].disabled=True
        add('tasting_score','Дотоод амталгааны үнэлгээ (1–5)','1.1',num(1,5))
        add('taster_count','Амтлагчдын тоо (оруулбал 5-аас доошгүй)','1.1',forms.IntegerField(min_value=5))
        add('consumer_test','Тестэд оролцсон хэрэглэгчдийн тоо','1.2',forms.IntegerField(min_value=1))
        add('consumer_liking','Таалагдсан үнэлгээ (1–9)','1.2',num(1,9))
        add('consumer_would_buy_percent','Зорилтот үнээр худалдан авах хувь (%)','1.2',num(0,100))
        add('typed_cogs','COGS гараар оруулах (₮, заавал биш)','1.3',num())
        for key,label in [('estimated_cogs_vs_limit','Тооцоолсон COGS (₮)'),('cogs_limit','Gate 0 COGS хязгаар (₮)'),('cogs_status','COGS төлөв'),('cogs_source','COGS эх үүсвэр')]:
            add(key,label,'1.3',forms.CharField(disabled=True))
        self.fields['cogs_status'].help_text+=' Хязгаар эсвэл Green/Amber босго байхгүй бол хүлээгдэж байна гэж харуулна.'
        add('cogs_reason','Amber / Red шалтгаан','1.3',text())
        add('cogs_action','Amber / Red үед авах арга хэмжээ','1.3',text())
        add('raw_material_spec_price_moq_second_source','Шинэ эсвэл өөрчлөгдсөн түүхий эд','1.4',RowsField(MaterialRow,required=False,complete=False))
        add('capacity_equipment_fit','Үйлдвэрлэлийн шугам','1.5',text())
        add('capacity_units_day','Хүчин чадал (ширхэг / өдөр)','1.5',num())
        add('shift_count','Ээлжийн тоо','1.5',forms.IntegerField(min_value=0))
        add('capacity_constraint','Хязгаарлалт','1.5',enum([('cooling','Хөргөлт'),('packing','Савлагаа'),('space','Талбай'),('labour','Хөдөлмөр'),('other','Бусад')]))
        add('constraint_details','Хязгаарлалтын тайлбар','1.5',text())
        for hour in [0,72]:
            for key,label in [('texture','Бүтэц'),('taste','Амт'),('appearance','Гадаад байдал'),('water_release','Ус ялгаралт')]:
                add('fridge_%s_%s'%(hour,key),'%s цаг · %s'%(hour,label),'1.6',text())
            add('fridge_check_72h' if hour==72 else 'fridge_0_result','%s цаг · Шалгалтын үр дүн'%hour,'1.6',enum([('pass','Тэнцсэн'),('fail','Тэнцээгүй')]))
        add('shelf_life_test_plan','Лаборатори','1.7',text())
        add('shelf_life_test_days','Тестийн хугацаа (хоног)','1.7',forms.IntegerField(min_value=1))
        add('shelf_life_result_due','Үр дүн гарах огноо','1.7',date())
        add('qa_requirements_issued','Хориглосон орцыг шалгасан эсэх','1.8',enum(yesno))
        add('process_flow_ccp_issued','Процессын урсгал ба CCP шаардлага гаргасан эсэх','1.8',enum(yesno))
        add('packaging_label_concept','Савлагааны төрөл','1.9',enum([(item.code,item.name) for item in PackagingType.objects.filter(active=True)]))
        self.fields['packaging_label_concept'].help_text+=' Савлагааны төрлийг удирдлагын самбарт тохируулна.'
        add('pack_size','Савлагааны хэмжээ','1.9',text())
        add('pack_material','Савлагааны материал','1.9',text())
        add('material_certificate','Материалын гэрчилгээ байгаа эсэх','1.9',enum(yesno))
        add('marketing_name','Маркетингийн нэр','1.10',text())
        add('marketing_key_message','Гол мессеж','1.10',text())
        add('marketing_brief','Нэвтрүүлэх санаа','1.10',text())
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
        self.initial.update(cost_comparison(food,raw))

    def clean(self):
        data=super().clean()
        data.update(cost_comparison(self.food,data.get('typed_cogs')))
        # All fields remain optional, including follow-up reasons/actions.
        return data
