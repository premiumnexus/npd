from datetime import timedelta
from decimal import Decimal
import json
from django import forms
from django.utils import timezone
from .models import Gate0Option, Supplier
from .gate0_rows import RowsField,EvidenceRow,CompetitorRow,AnalogRow,CannibalisationRow

class DaypartChoiceField(forms.MultipleChoiceField):
    def to_python(self, value):
        # Existing briefs and older clients contain one daypart as a string.
        if isinstance(value, str) and value:
            value = [value]
        return super().to_python(value)


class Gate0Form(forms.Form):
    identity_keys = ('product_name', 'product_type', 'category', 'subcategory', 'product_role', 'planned_launch_date')
    customer_keys = ('customer_segment', 'target_customer_occasion', 'daypart', 'evidence')
    pricing_keys = ('competitor_benchmark', 'target_shelf_price', 'vat_percent', 'cu_margin', 'vendor_rebate', 'vendor_margin', 'price_excl_vat', 'max_invoice_price', 'cu_total_margin', 'cogs_limit')
    sales_keys = ('analog_skus_sales_target', 'target_units_store_day', 'store_scope', 'store_cluster', 'store_count', 'cannibalisation', 'day45_writeoff_percent', 'day45_margin_percent')
    supply_keys = ('producer', 'new_supplier', 'raw_materials_supply_risk', 'seasonal_price_swing', 'moq', 'first_capacity_check', 'capacity_units_day')
    safety_keys = ('first_food_safety_risk', 'high_risk_inputs', 'shelf_life_hours', 'technical_risk_measure')
    required_keys = identity_keys[:-1] + ('customer_segment', 'daypart', 'target_shelf_price', 'cu_margin', 'vendor_rebate', 'vendor_margin', 'target_units_store_day') + supply_keys[:3] + safety_keys[:2]

    @property
    def identity_fields(self):
        return [self[key] for key in self.identity_keys]

    @property
    def customer_fields(self):
        return [self[key] for key in self.customer_keys]

    @property
    def pricing_fields(self):
        return [self[key] for key in self.pricing_keys]

    @property
    def sales_fields(self):
        return [self[key] for key in self.sales_keys]

    @property
    def supply_fields(self):
        return [self[key] for key in self.supply_keys]

    @property
    def safety_fields(self):
        return [self[key] for key in self.safety_keys]

    @property
    def legacy_analog_files(self):
        return list(self.food.gate0_files.filter(slot_code='G0-F4',analog_rows__isnull=True)) if self.food else []

    @property
    def legacy_evidence_files(self):
        return list(self.food.gate0_files.filter(slot_code='G0-F1',evidence_rows__isnull=True)) if self.food else []

    @property
    def legacy_competitor_files(self):
        return list(self.food.gate0_files.filter(slot_code='G0-F2',competitor_rows__isnull=True)) if self.food else []

    @property
    def remaining_fields(self):
        return [field for field in self if field.name not in self.identity_keys + self.customer_keys + self.pricing_keys + self.sales_keys + self.supply_keys + self.safety_keys]

    def __init__(self,*args,food=None,submission=False,**kwargs):
        super().__init__(*args,**kwargs)
        evidence_keys=EvidenceRow.evidence_keys
        if self.is_bound and 'evidence' not in self.data and 'evidence-TOTAL_FORMS' not in self.data:
            self.data=self.data.copy()
            self.data['evidence']=[{key:self.data.get(key,'') for key in evidence_keys}]
        if not self.is_bound and not self.initial.get('evidence'):
            legacy={key:self.initial.get(key,'') for key in evidence_keys}
            if any(legacy.values()): self.initial['evidence']=[legacy]
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
        self.fields['product_type'].help_text+=' Gate 0 илгээсний дараа түгжинэ.'
        self.locked_product_type = None
        if food and food.gate0_submitted_at:
            from .gate0 import initial_brief
            self.locked_product_type = initial_brief(food).get('product_type')
            self.fields['product_type'].disabled=bool(self.locked_product_type)
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
        add('customer_segment','Зорилтот хэрэглэгчийн сегмент','2.1',enum(choices('segment'),required))
        add('daypart','Хэрэглээний үе','2.3',DaypartChoiceField(choices=[('morning','Өглөө'),('lunch','Өдөр'),('evening','Орой'),('late','Шөнө')],required=required,widget=forms.SelectMultiple(attrs={'data-multiselect':True})))
        add('target_customer_occasion','Зорилтот хэрэглэгч, хэрэглээний тайлбар','2.2',text())
        add('evidence','Нотолгоо','2.4',RowsField(EvidenceRow,required=False,complete=False))
        add('competitor_benchmark','Өрсөлдөгчийн жишиг','0.7',RowsField(CompetitorRow,required=False,complete=False))
        add('target_shelf_price','Зорилтот тавиурын үнэ (НӨАТ-тай, ₮)','0.8',forms.IntegerField(min_value=1,required=required))
        add('cu_margin','CU-ийн ашгийн хувь','0.9',number(60,1,required))
        self.fields['cu_margin'].help_text+=' НӨАТ-гүй тавиурын үнээс, rebate-ийн өмнө. SKU тутамд.'
        add('vendor_rebate','Rebate % (0 байж болно)','0.10',number(30,2,required))
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
        add('analog_skus_sales_target','Жишиг SKU','4.1',RowsField(AnalogRow,minimum=0,maximum=3,complete=False,required=False,help_text='3 хүртэл мөр, заавал биш'))
        add('target_units_store_day','Зорилтот APSD (ширхэг / дэлгүүр / өдөр)','0.14',number(None,2,required))
        add('store_scope','Дэлгүүрийн хамрах хүрээ','0.15',enum([('all','Бүх дэлгүүр'),('cluster','Кластер'),('pilot','Сонгосон дэлгүүр (туршилт)')],required))
        add('store_cluster','Дэлгүүрийн кластер','0.15',enum(choices('cluster')))
        add('store_count','Дэлгүүрийн тоо','0.15',forms.IntegerField(min_value=1,required=required))
        add('cannibalisation','Каннибализаци (мөр): нөлөөлөх SKU · борлуулалтаас авах %','4.6',RowsField(CannibalisationRow,complete=False,required=False))
        yesno=[('yes','Тийм'),('no','Үгүй')]
        add('raw_materials_supply_risk','Шинэ түүхий эд байгаа эсэх','0.17',enum(yesno,required))
        add('new_supplier','Шинэ нийлүүлэгч байгаа эсэх','0.17',enum(yesno,required))
        add('seasonal_price_swing','Улирлын үнийн хэлбэлзэл байгаа эсэх','0.17',enum(yesno,required))
        add('moq','Захиалгын доод хэмжээ (MOQ)','0.17',number(None,2,required))
        add('first_capacity_check','Нийлүүлэгчийн хүчин чадлын анхны үнэлгээ','5.6',enum([('available', 'Боломжтой'),('unavailable','Боломжгүй'),('conditional','Нөхцөлтэй')],required))
        add('capacity_units_day','Нийлүүлэгчийн хүчин чадал (ширхэг/өдөр)','5.7',number(None,2,required))
        add('first_food_safety_risk','Харшил үүсгэгч','0.19',forms.MultipleChoiceField(choices=choices('allergen'),required=False,widget=forms.CheckboxSelectMultiple))
        add('high_risk_inputs','Өндөр эрсдэлтэй орц','0.19',forms.MultipleChoiceField(choices=choices('high_risk'),required=False,widget=forms.CheckboxSelectMultiple))
        add('shelf_life_hours','Хадгалах хугацаа (цаг)','6.3',forms.IntegerField(min_value=1,required=False))
        add('technical_risk_measure','Шинжилгээ, хэмжилтээр шалгах технологийн эрсдэл','0.20',text())
        add('day45_writeoff_percent','45 хоногийн акт %','4.7',number(100,1,required))
        add('day45_margin_percent','45 хоногийн актын дараах ашиг % (= 3.9 − 4.7)','4.8',forms.CharField(required=False,disabled=True,help_text='3.9 − 4.7'))
        from .target_costing import after_writeoff_margin
        sales_margin=after_writeoff_margin(calculated['cu_total_margin'],self.data.get('day45_writeoff_percent') if self.is_bound else self.initial.get('day45_writeoff_percent'))
        self.initial['day45_margin_percent']=format(sales_margin.quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'f') if sales_margin is not None else ''
        self.fields['day45_margin_percent'].widget.attrs.update({'class':'costing-result','data-costing-output':'day45_margin_percent'})
        add('planned_launch_date','Төлөвлөсөн нэвтрүүлэх огноо','0.22',forms.DateField(required=required,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'})))
        self.fields['planned_launch_date'].help_text+=' Өнөөдрөөс 30 хоногийн дотор байвал анхааруулна. Илгээхийг хориглохгүй.'
        from .dropdown_options import apply_options
        apply_options(self, 'gate0')
        for section, keys in ((1,self.identity_keys),(2,self.customer_keys),(3,self.pricing_keys),(4,self.sales_keys),(5,self.supply_keys),(6,self.safety_keys)):
            for index, key in enumerate(keys, start=1):
                field = self.fields[key]
                number = f'{section}.{index}'
                field.help_text = field.help_text.replace(field.gate_number + ' · ', number + ' · ', 1)
                field.gate_number = number
                field.gate_required = key in self.required_keys
                field.required = submission and field.gate_required
        self.order_fields(self.identity_keys + self.customer_keys + self.pricing_keys + self.sales_keys + self.supply_keys + self.safety_keys)
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
        first_evidence=next(iter(data.get('evidence') or []),{})
        from .models import Gate0File
        for key,slot in [('evidence','G0-F1'),('competitor_benchmark','G0-F2'),('analog_skus_sales_target','G0-F4')]:
            attachments={row['attachment'] for row in data.get(key,[]) if row.get('attachment')}
            allowed=set(Gate0File.objects.filter(development=self.food,slot_code=slot,pk__in=attachments).values_list('pk',flat=True)) if self.food else set()
            if attachments-allowed:
                self.add_error(key,'Хавсралт энэ бүтээгдэхүүний талбарт хамаарахгүй байна.')
        for key in EvidenceRow.evidence_keys:
            data[key]=first_evidence.get(key,'')
        kind=data.get('product_type')
        if kind == 'new':
            for key in ['existing_sku','improvement_reasons','improvement_reason']: data[key]=[] if key=='improvement_reasons' else ''
        # New/improvement is a workflow route, independent of FF/ISF category.
        if self.locked_product_type:
            if data.get('product_type') != self.locked_product_type:
                self.add_error('product_type','Gate 0 илгээсний дараа төрлийг өөрчлөх боломжгүй.')
        from .target_costing import calculate,after_writeoff_margin
        data.update(calculate(data,self.vat_percent))
        data['day45_margin_percent']=after_writeoff_margin(data['cu_total_margin'],data.get('day45_writeoff_percent'))
        return data

    @property
    def launch_warning(self):
        value=self.cleaned_data.get('planned_launch_date') if hasattr(self,'cleaned_data') else None
        return bool(value and timezone.localdate() <= value <= timezone.localdate()+timedelta(days=30))
