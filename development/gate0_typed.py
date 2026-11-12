from datetime import timedelta
from decimal import Decimal
import json
from django import forms
from django.utils import timezone
from .models import Gate0Option, Supplier
from .gate0_rows import RowsField,CompetitorRow,AnalogRow,CannibalisationRow

class DaypartChoiceField(forms.MultipleChoiceField):
    def to_python(self, value):
        # Existing briefs and older clients contain one daypart as a string.
        if isinstance(value, str) and value:
            value = [value]
        return super().to_python(value)


class Gate0Form(forms.Form):
    def __init__(self,*args,food=None,submission=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.food=food
        self.submission=submission
        options=list(Gate0Option.objects.filter(active=True))
        def choices(kind,category=None):
            return [(item.code,item.label) for item in options if item.kind==kind and (category is None or item.category==category)]
        selected_category=(self.data.get('category') if self.is_bound else self.initial.get('category'))
        def add(key,label,number,field):
            field.label=label
            field.gate_number=number
            field.help_text=number+' · '+str(field.help_text or '')
            self.fields[key]=field
        def text(required=False): return forms.CharField(required=required,widget=forms.Textarea(attrs={'rows':2}))
        def enum(items,required=False): return forms.ChoiceField(choices=[('','---------')]+items,required=required)
        def number(maximum=None,places=1,required=False): return forms.DecimalField(min_value=0,max_value=maximum,decimal_places=places,max_digits=14,required=required)
        required=False
        add('product_type','Шинэ эсвэл сайжруулалт','0.2',enum([('new','Шинэ'),('improvement','Сайжруулалт')],False))
        self.fields['product_type'].help_text+=' Сонголт заавал биш. Gate 0 илгээсний дараа түгжинэ.'
        if food and food.gate0_submitted_at:
            self.fields['product_type'].disabled=True
        add('existing_sku','Одоо байгаа SKU код','0.2',text())
        add('product_name','Бүтээгдэхүүний нэр','0.1',forms.CharField(max_length=160,required=required))
        add('category','Ангилал','0.1',enum([('FF','FF'),('ISF','ISF')],required))
        add('subcategory','Дэд ангилал','0.1',enum(choices('subcategory',selected_category),required))
        self.fields['subcategory'].widget.attrs['data-options']=json.dumps([{'code':item.code,'label':item.label,'category':item.category} for item in options if item.kind=='subcategory'],ensure_ascii=False)
        self.fields['subcategory'].help_text+=' Жагсаалтыг удирдлагын самбарт ангилал тус бүрээр тохируулна.'
        add('improvement_reasons','Сайжруулалтын шалтгааны код','0.3',forms.MultipleChoiceField(choices=choices('improvement_reason'),required=False,widget=forms.CheckboxSelectMultiple))
        add('improvement_reason','Юу өөрчлөх, яагаад өөрчлөх тайлбар','0.3',text())
        add('product_role','Бүтээгдэхүүний үүрэг','0.4',enum(choices('product_role'),required))
        self.fields['product_role'].help_text+=' Тайлан, шүүлтэд ашиглана. Ашгийн тооцоонд нөлөөлөхгүй.'
        add('customer_segment','Зорилтот хэрэглэгчийн сегмент','0.5',enum(choices('segment'),required))
        add('daypart','Хэрэглээний үе','0.5',DaypartChoiceField(choices=[('morning','Өглөө'),('lunch','Өдөр'),('evening','Орой'),('late','Шөнө')],required=required,widget=forms.SelectMultiple(attrs={'data-multiselect':True})))
        add('target_customer_occasion','Зорилтот хэрэглэгч, хэрэглээний тайлбар','0.5',text())
        add('customer_need_evidence','Хэрэглээний нотолгоо','0.6',text(required))
        add('evidence_level','Нотолгооны төрөл','0.6',enum([('A','A · POS / борлуулалтын өгөгдөл'),('B','B · Хэрэглэгчийн судалгаа'),('C','C · Дэлгүүрийн хүсэлт'),('D','D · Өрсөлдөгчийн үнэ'),('E','E · борлуулалт'),('F','F · Гадаад CU/BGF борлуулалт'),('G','G · Тренд')],required))
        add('evidence_reference','Нотолгооны эх сурвалж','0.6',text())
        add('competitor_benchmark','Өрсөлдөгчийн жишиг','0.7',RowsField(CompetitorRow,required=False,complete=False))
        add('target_shelf_price','Зорилтот тавиурын үнэ (НӨАТ-тай, ₮)','0.8',forms.IntegerField(min_value=1,required=required))
        add('cu_margin','CU-ийн ашгийн хувь','0.9',number(60,1,required))
        self.fields['cu_margin'].help_text+=' НӨАТ-гүй тавиурын үнээс, rebate-ийн өмнө. SKU тутамд.'
        add('vendor_rebate','Rebate (буцаан олголт) %','0.10',number(30,2,required))
        self.fields['vendor_rebate'].help_text+=' Нэхэмжлэхийн үнийн хувь. 0 байж болно. Нийлүүлэгчээс CU-д төлнө.'
        add('producer','Үйлдвэрлэгч','0.11',enum([('central_foods','Central Foods')]+[('supplier:%s' % item.pk,item.name) for item in Supplier.objects.all()],required))
        add('vendor_margin','Нийлүүлэгчийн ашгийн хувь','0.12',number(60,2,required))
        self.fields['vendor_margin'].help_text+=' Rebate-ийн дараах цэвэр орлогоос. Хөдөлмөр, эрчим хүч, нэмэгдэл зардал, ашгийг багтаана.'
        from .target_costing import calculate, vat_rate
        self.vat_percent=vat_rate()
        calculated=calculate(self.data if self.is_bound else self.initial,self.vat_percent)
        specs=[
            ('vat_percent','VAT / НӨАТ (%)','VAT','Удирдлагын тохиргоо',2),
            ('price_excl_vat','НӨАТ-гүй үнэ (₮)','C01','Зорилтот тавиурын үнэ (НӨАТ-тай, ₮) / (1 + VAT / НӨАТ (%) / 100)',0),
            ('max_invoice_price','Нийлүүлэгчийн нэхэмжлэхийн дээд үнэ (₮)','C02','НӨАТ-гүй үнэ (₮) × (1 − CU-ийн ашгийн хувь / 100)',0),
            ('cogs_limit','COGS-ийн дээд хязгаар (₮)','0.13','Нийлүүлэгчийн нэхэмжлэхийн дээд үнэ (₮) × (1 − Rebate (буцаан олголт) % / 100) × (1 − Нийлүүлэгчийн ашгийн хувь / 100)',0),
            ('cu_total_margin','Rebate орсон CU нийт ашгийн хувь (%)','C04','(1 − (1 − CU-ийн ашгийн хувь / 100) × (1 − Rebate (буцаан олголт) % / 100)) × 100',1),
        ]
        from decimal import ROUND_HALF_UP
        for key,label,identifier,formula,places in specs:
            add(key,label,identifier,forms.CharField(required=False,disabled=True,help_text=formula))
            if key != 'vat_percent': self.fields[key].help_text=formula
            value=calculated[key]
            self.initial[key]=format(value.quantize(Decimal('1').scaleb(-places),rounding=ROUND_HALF_UP),'f') if value is not None else ''
            self.fields[key].widget.attrs.update({'class':'costing-setting' if key=='vat_percent' else 'costing-result','data-costing-output':key})
        for key in ['target_shelf_price','cu_margin','vendor_rebate','vendor_margin']:
            self.fields[key].widget.attrs['class']='costing-input'
        add('analog_skus_sales_target','Жишиг SKU (3 хүртэл мөр, заавал биш)','0.14',RowsField(AnalogRow,minimum=0,maximum=3,complete=False,required=False))
        add('target_units_store_day','Зорилтот APSD (ширхэг / дэлгүүр / өдөр)','0.14',number(None,2,required))
        add('store_scope','Дэлгүүрийн хамрах хүрээ','0.15',enum([('all','Бүх дэлгүүр'),('cluster','Кластер'),('pilot','Сонгосон дэлгүүр (туршилт)')],required))
        add('store_cluster','Дэлгүүрийн кластер','0.15',enum(choices('cluster')))
        add('store_count','Дэлгүүрийн тоо','0.15',forms.IntegerField(min_value=1,required=required))
        add('cannibalisation','Каннибализаци','0.16',RowsField(CannibalisationRow,complete=False,required=False))
        yesno=[('yes','Тийм'),('no','Үгүй')]
        add('raw_materials_supply_risk','Шинэ түүхий эд байгаа эсэх','0.17',enum(yesno,required))
        add('new_supplier','Шинэ нийлүүлэгч байгаа эсэх','0.17',enum(yesno,required))
        add('seasonal_price_swing','Улирлын үнийн хэлбэлзэл байгаа эсэх','0.17',enum(yesno,required))
        add('moq','Захиалгын доод хэмжээ (MOQ)','0.17',number(None,2,required))
        add('first_capacity_check','Хүчин чадлын анхны үнэлгээ','0.18',enum([('available', 'Боломжтой'),('unavailable','Боломжгүй'),('conditional','Нөхцөлтэй')],required))
        add('capacity_units_day','Хүчин чадал (ширхэг / өдөр)','0.18',number(None,2,required))
        add('first_food_safety_risk','Харшил үүсгэгч','0.19',forms.MultipleChoiceField(choices=choices('allergen'),required=False,widget=forms.CheckboxSelectMultiple))
        add('high_risk_inputs','Өндөр эрсдэлтэй орц','0.19',forms.MultipleChoiceField(choices=choices('high_risk'),required=False,widget=forms.CheckboxSelectMultiple))
        add('shelf_life_days','Хадгалах хугацаа (хоног, шаардлагатай бол)','0.19',forms.IntegerField(min_value=1,required=False))
        add('technical_risk_measure','Шинжилгээ, хэмжилтээр шалгах технологийн эрсдэл','0.20',text())
        add('day45_success_criteria','45 хоногийн зорилт (ширхэг / дэлгүүр / өдөр)','0.21',number(None,2,required))
        add('day45_writeoff_percent','45 хоногийн акт (өртгийн %)','0.21',number(100,1,required))
        add('day45_margin_percent','45 хоногийн акт-ын дараах ашиг (%)','0.21',forms.DecimalField(decimal_places=2,max_digits=14,required=required))
        add('planned_launch_date','Төлөвлөсөн нэвтрүүлэх огноо','0.22',forms.DateField(required=required,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'})))
        self.fields['planned_launch_date'].help_text+=' Өнөөдрөөс 30 хоногийн дотор байвал анхааруулна. Илгээхийг хориглохгүй.'
        from .dropdown_options import apply_options
        apply_options(self, 'gate0')
        self.legacy_values=[]
        # Keep unconverted old text visible for manual conversion; never infer numbers.
        if not self.is_bound:
            for key,field in self.fields.items():
                value=self.initial.get(key)
                if value in (None,'',[]): continue
                try:
                    if isinstance(field,RowsField) and not isinstance(value,list): raise ValueError()
                    field.clean(value)
                except (forms.ValidationError,ValueError,TypeError):
                    self.legacy_values.append((field.label,value))
                    self.initial[key]=[] if isinstance(field,(RowsField,forms.MultipleChoiceField)) else ''

    def clean(self):
        data=super().clean()
        kind=data.get('product_type')
        if kind == 'new':
            for key in ['existing_sku','improvement_reasons','improvement_reason']: data[key]=[] if key=='improvement_reasons' else ''
        # New/improvement is a workflow route, independent of FF/ISF category.
        if self.food and self.food.gate0_submitted_at:
            from .gate0 import initial_brief
            if data.get('product_type') != initial_brief(self.food).get('product_type'):
                self.add_error('product_type','Gate 0 илгээсний дараа төрлийг өөрчлөх боломжгүй.')
        from .target_costing import calculate
        data.update(calculate(data,self.vat_percent))
        return data

    @property
    def launch_warning(self):
        value=self.cleaned_data.get('planned_launch_date') if hasattr(self,'cleaned_data') else None
        return bool(value and timezone.localdate() <= value <= timezone.localdate()+timedelta(days=30))
