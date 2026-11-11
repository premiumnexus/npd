from datetime import date
from decimal import Decimal, InvalidOperation
from django import forms

def gate0_targets(food):
    from .gate0 import initial_brief
    data=initial_brief(food) if food else {}
    return {'day45_units_store_day':data.get('day45_success_criteria'), 'day45_writeoff_percent':data.get('day45_writeoff_percent'),'day45_margin_percent':data.get('day45_margin_percent'),'original_launch_date':data.get('planned_launch_date')}

def derived_values(food,typed_cogs,launch_date,vendor_invoice_price=None):
    from .gate1 import initial_brief
    def decimal(value):
        try:
            result=Decimal(str(value))
            return result if result.is_finite() else None
        except (InvalidOperation,ValueError,TypeError): return None
    from .gate1_typed import cost_comparison
    from .gate0 import initial_brief as gate0_data
    from .target_costing import calculate
    gate1=initial_brief(food) if food else {}
    cogs=cost_comparison(food,gate1.get('typed_cogs'))['estimated_cogs_vs_limit']
    target=gate0_data(food) if food else {}
    target_calcs=calculate(target,target.get('vat_percent'))
    net=target_calcs['price_excl_vat']
    invoice=decimal(vendor_invoice_price)
    rebate=decimal(target.get('vendor_rebate'))
    margin=decimal(target.get('cu_margin'))
    front=(1-invoice/net)*100 if invoice is not None and net is not None and net>0 else None
    gap=max(Decimal(0),margin-front) if margin is not None and front is not None else None
    retained=invoice*(1-rebate/100) if invoice is not None and rebate is not None else None
    vendor=(1-cogs/retained)*100 if cogs is not None and retained is not None and retained>0 else None
    original=gate0_targets(food)['original_launch_date']
    try: planned=date.fromisoformat(str(original))
    except (ValueError,TypeError): planned=None
    try: actual=launch_date if isinstance(launch_date,date) else date.fromisoformat(str(launch_date))
    except (ValueError,TypeError): actual=None
    return {'final_cogs_invoice_price':cogs,'original_launch_date':original or '',
            'launch_delay_days':(actual-planned).days if actual and planned else '',
            'front_margin_percent':front,'margin_gap_points':gap,'implied_vendor_margin_percent':vendor}


class Gate2Form(forms.Form):
    def __init__(self,*args,food=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.food=food
        def add(key,label,number,field):
            field.required=False
            field.label=label
            field.help_text=number+' · '+str(field.help_text or '')
            self.fields[key]=field
        def text(): return forms.CharField(widget=forms.Textarea(attrs={'rows':2}))
        def number(minimum=0,maximum=None,places=2): return forms.DecimalField(min_value=minimum,max_value=maximum,decimal_places=places,max_digits=14)
        def integer(): return forms.IntegerField(min_value=0)
        def enum(items): return forms.ChoiceField(choices=[('','---------')]+items)
        def datefield(): return forms.DateField(widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
        yesno=[('yes','Тийм'),('no','Үгүй')]
        passfail=[('pass','Тэнцсэн'),('fail','Тэнцээгүй')]
        add('mass_trial_result','Масс туршилтын багц (кг)','2.1',number(0,None,3))
        add('trial_yield_percent','Туршилтын гарц (%)','2.1',number(0,100))
        add('unit_weight_mean','Нэгжийн дундаж жин (г)','2.1',number(0,None,3))
        add('unit_weight_variation','Нэгжийн жингийн хэлбэлзэл (± г)','2.1',number(0,None,3))
        add('trial_taste_score','Амтын үнэлгээ (1–5)','2.1',number(1,5))
        add('trial_date','Туршилтын огноо','2.1',datefield())
        add('final_recipe_version','Эцсийн жорын хувилбар','2.2',forms.IntegerField(min_value=1))
        if food and food.recipe_version is not None:
            self.initial['final_recipe_version']=food.recipe_version
            self.fields['final_recipe_version'].disabled=True
        add('vendor_invoice_price','Нийлүүлэгчийн нэхэмжлэхийн үнэ (₮)','2.2',number())
        add('final_cogs_invoice_price','Эцсийн COGS (₮, Gate 1 жороос)','2.2',forms.CharField(disabled=True))
        add('front_margin_percent','Бодит үнээрх CU ашгийн хувь (%)','C13',forms.CharField(disabled=True))
        add('margin_gap_points','CU ашгийн зорилтоос дутсан зөрүү (нэгж хувь)','C14',forms.CharField(disabled=True))
        add('implied_vendor_margin_percent','Бодит үнээрх нийлүүлэгчийн ашгийн хувь (%)','C15',forms.CharField(disabled=True))
        formulas={
            'final_cogs_invoice_price':'Gate 1 жорын COGS = орцын өртгийн нийлбэр + нэгжийн савлагаа',
            'front_margin_percent':'(1 − Нийлүүлэгчийн нэхэмжлэхийн үнэ / НӨАТ-гүй үнэ) × 100',
            'margin_gap_points':'max(0, CU-ийн зорилтот ашгийн хувь − Бодит үнээрх CU ашгийн хувь)',
            'implied_vendor_margin_percent':'(1 − Эцсийн COGS / (Нийлүүлэгчийн нэхэмжлэхийн үнэ × (1 − Rebate (буцаан олголт) % / 100))) × 100',
        }
        for key,formula in formulas.items(): self.fields[key].help_text=formula
        self.fields['vendor_invoice_price'].widget.attrs['class']='costing-input'
        from .gate0 import initial_brief as gate0_data
        from .target_costing import calculate
        target=gate0_data(food) if food else {}
        net=calculate(target,target.get('vat_percent'))['price_excl_vat']
        self.fields['vendor_invoice_price'].widget.attrs.update({
            'data-net-price':str(net) if net is not None else '',
            'data-rebate':str(target.get('vendor_rebate')) if target.get('vendor_rebate') is not None else '',
            'data-target-margin':str(target.get('cu_margin')) if target.get('cu_margin') is not None else '',
        })
        for key in ['final_cogs_invoice_price','front_margin_percent','margin_gap_points','implied_vendor_margin_percent']:
            self.fields[key].widget.attrs['class']='costing-result'
        add('lab_results_approved_shelf_life','Микробиологийн шинжилгээ','2.3',enum(passfail))
        add('chemical_lab_result','Химийн шинжилгээ','2.3',enum(passfail))
        add('approved_shelf_life_days','Батлагдсан хадгалах хугацаа (хоног)','2.3',forms.IntegerField(min_value=1))
        add('final_technology_transfer_document','Технологи шилжүүлэх баримтын хувилбар','2.4',text())
        add('technology_transfer_date','Баримтын огноо','2.4',datefield())
        add('signed_npd','NPD гарын үсэг зурсан эсэх','2.4',enum(yesno))
        add('signed_qa','QA гарын үсэг зурсан эсэх','2.4',enum(yesno))
        add('signed_producer','Үйлдвэрлэгч гарын үсэг зурсан эсэх','2.4',enum(yesno))
        add('label_check','Шошгон дээрх бүтээгдэхүүний нэр','2.5',text())
        add('label_ingredients','Шошгон дээрх орцын жагсаалт','2.5',text())
        add('label_allergens','Орцын жагсаалтад мэдэгдсэн харшил үүсгэгчид (MNS 6648:2016)','2.5',text())
        add('label_weight','Шошгон дээрх жин (г)','2.5',number(0,None,3))
        add('label_dates','Шошгон дээрх огнооны мэдээлэл','2.5',text())
        add('label_lot_code','Шошгон дээрх багцын код','2.5',text())
        add('label_checked','Шошгыг шалгасан эсэх','2.5',enum(yesno))
        add('barcode_system_registration','Баркод','2.6',forms.CharField())
        add('sku_code_requested','SKU код хүссэн эсэх','2.6',enum(yesno))
        add('pos_name_price_checked','POS нэр, үнийг шалгасан эсэх','2.6',enum(yesno))
        add('allocation','Дэлгүүрийн тоо','2.7',integer())
        add('first_order_units','Эхний захиалга (ширхэг)','2.7',integer())
        add('allocation_units_store_day','Зорилт (ширхэг / дэлгүүр / өдөр)','2.7',number())
        add('supply_readiness','Эхний 2 долоо хоногийн түүхий эд бэлэн эсэх','2.8',enum(yesno))
        add('delivery_slot','Хүргэлтийн цагийн хуваарь','2.8',text())
        add('cold_chain_temperature','Хүйтэн хэлхээний температур (°C)','2.8',forms.DecimalField(max_digits=6,decimal_places=2))
        add('marketing_plan','Маркетингийн сувгууд','2.9',text())
        add('marketing_promotion','Урамшуулал','2.9',text())
        add('marketing_start_date','Маркетинг эхлэх огноо','2.9',datefield())
        add('marketing_end_date','Маркетинг дуусах огноо','2.9',datefield())
        add('quality_tolerance_baseline','Жингийн зорилт (г)','2.10',number(0,None,3))
        add('quality_weight_min','Жингийн доод хязгаар (г)','2.10',number(0,None,3))
        add('quality_weight_max','Жингийн дээд хязгаар (г)','2.10',number(0,None,3))
        add('quality_texture_target','Бүтцийн зорилт','2.10',text())
        add('quality_texture_range','Бүтцийн зөвшөөрөх хүрээ','2.10',text())
        add('quality_taste_target','Амтын зорилт','2.10',text())
        add('quality_taste_range','Амтын зөвшөөрөх хүрээ','2.10',text())
        add('day45_target_confirmed','45 хоногийн зорилтын сонголт','2.11',enum([('same','Gate 0 (0.21)-тэй ижил'),('changed','Өөрчилсөн')]))
        add('day45_units_store_day','45 хоногийн зорилт (ширхэг / дэлгүүр / өдөр)','2.11',number())
        add('day45_writeoff_percent','45 хоногийн write-off (өртгийн %)','2.11',number(0,100))
        add('day45_margin_percent','45 хоногийн write-off-ын дараах ашиг (%)','2.11',forms.DecimalField(max_digits=14,decimal_places=2))
        add('day45_change_reason','45 хоногийн зорилт өөрчилсөн шалтгаан','2.11',text())
        self.fields['day45_change_reason'].help_text+=' Өөрчилсөн бол тайлбар оруулж болно. Талбар заавал биш.'
        add('original_launch_date','Gate 0 (0.22) төлөвлөсөн огноо','2.12',forms.CharField(disabled=True))
        add('launch_date','Нэвтрүүлэх огноо','2.12',datefield())
        add('launch_delay_days','Төлөвлөгөөнөөс зөрсөн хоног (+ хойшилсон / − урагшилсан)','2.12',forms.CharField(disabled=True))
        add('launch_date_change_reason','Нэвтрүүлэх огноо өөрчилсөн шалтгаан','2.12',text())
        self.fields['launch_date_change_reason'].help_text+=' Огноо зөрвөл тайлбар оруулж болно. Талбар заавал биш.'
        self.legacy_values=[]
        if not self.is_bound:
            for key,field in self.fields.items():
                value=self.initial.get(key)
                if value in (None,'',[]): continue
                try: field.clean(value)
                except (forms.ValidationError,ValueError,TypeError):
                    self.legacy_values.append((field.label,value))
                    self.initial[key]=''
        same=(self.data.get('day45_target_confirmed') if self.is_bound else self.initial.get('day45_target_confirmed')) == 'same'
        targets=gate0_targets(food)
        for key in ['day45_units_store_day','day45_writeoff_percent','day45_margin_percent']:
            self.fields[key].widget.attrs['data-gate0-value']=str(targets[key] if targets[key] is not None else '')
        if same:
            for key in ['day45_units_store_day','day45_writeoff_percent','day45_margin_percent']:
                self.initial[key]=targets[key]
                self.fields[key].disabled=True
        raw=self.data if self.is_bound else self.initial
        self.initial.update(derived_values(food,None,raw.get('launch_date'),raw.get('vendor_invoice_price')))
        cogs=self.initial['final_cogs_invoice_price']
        self.fields['vendor_invoice_price'].widget.attrs['data-final-cogs']=str(cogs) if cogs is not None else ''
        from decimal import ROUND_HALF_UP
        for key in ['final_cogs_invoice_price','front_margin_percent','margin_gap_points','implied_vendor_margin_percent']:
            value=self.initial[key]
            if value is not None:
                self.initial[key]=format(value.quantize(Decimal('1') if key=='final_cogs_invoice_price' else Decimal('0.1'),rounding=ROUND_HALF_UP),'f')

    def clean(self):
        data=super().clean()
        low,high=data.get('quality_weight_min'),data.get('quality_weight_max')
        target=data.get('quality_tolerance_baseline')
        if low is not None and high is not None and low>high:
            self.add_error('quality_weight_max','Дээд хязгаар доод хязгаараас бага байж болохгүй.')
        if target is not None and ((low is not None and target<low) or (high is not None and target>high)):
            self.add_error('quality_tolerance_baseline','Зорилтот жин зөвшөөрөх хүрээнд байна.')
        start,end=data.get('marketing_start_date'),data.get('marketing_end_date')
        if start and end and end<start:
            self.add_error('marketing_end_date','Дуусах огноо эхлэх огнооноос өмнө байж болохгүй.')
        data.update(derived_values(self.food,None,data.get('launch_date'),data.get('vendor_invoice_price')))
        return data
