from django import forms

class CompetitorRow(forms.Form):
    product=forms.CharField(label='Бүтээгдэхүүн')
    price=forms.IntegerField(label='Үнэ (₮)',min_value=1)
    weight_g=forms.DecimalField(label='Жин (г)',min_value=0,decimal_places=2,max_digits=12)

class AnalogRow(forms.Form):
    sku=forms.CharField(label='SKU код')
    units_per_store_day=forms.DecimalField(label='Ширхэг / дэлгүүр / өдөр (бодит)',min_value=0,decimal_places=2,max_digits=12)

class CannibalisationRow(forms.Form):
    sku=forms.CharField(label='Нөлөөлөх SKU код')
    sales_taken_percent=forms.DecimalField(label='Борлуулалтаас авах хувь (%)',min_value=0,max_value=100,decimal_places=1,max_digits=4)

class RowsWidget(forms.Widget):
    template_name='widgets/gate0_rows.html'
    def __init__(self,row_form,attrs=None):
        super().__init__(attrs)
        self.row_form=row_form
    def value_from_datadict(self,data,files,name):
        if name in data and isinstance(data[name],list): return data[name]
        try: total=min(max(int(data.get(name+'-TOTAL_FORMS',0)),0),100)
        except (ValueError,TypeError): total=0
        rows=[]
        for index in range(total):
            prefix='%s-%s-' % (name,index)
            if data.get(prefix+'DELETE'): continue
            rows.append({key:data.get(prefix+key,'') for key in self.row_form.base_fields})
        return rows
    def get_context(self,name,value,attrs):
        context=super().get_context(name,value,attrs)
        values=value if isinstance(value,list) else []
        values=values or [{}]
        disabled=bool((attrs or {}).get('disabled'))
        def row(data,prefix):
            form=self.row_form(initial=data,prefix=prefix)
            for field in form.fields.values():
                field.required=False
                field.disabled=disabled
            return form
        context['widget'].update(rows=[row(data,'%s-%s' % (name,index)) for index,data in enumerate(values)],empty=row({},name+'-__prefix__'),disabled=disabled)
        return context

class RowsField(forms.Field):
    def __init__(self,row_form,minimum=0,maximum=100,complete=False,**kwargs):
        self.row_form=row_form
        self.minimum=minimum
        self.maximum=maximum
        self.complete=complete
        super().__init__(widget=RowsWidget(row_form),**kwargs)
    def clean(self,value):
        if not isinstance(value,list): value=[]
        rows=[]
        for index,data in enumerate(value):
            if not isinstance(data,dict): raise forms.ValidationError('Мөрийн өгөгдөл буруу байна.')
            if not any(str(item).strip() for item in data.values() if item is not None): continue
            form=self.row_form(data)
            if not self.complete:
                for field in form.fields.values(): field.required=False
            if not form.is_valid():
                raise forms.ValidationError('%s-р мөр: %s' % (index+1,'; '.join('%s: %s' % (form.fields[key].label,', '.join(errors)) for key,errors in form.errors.items())))
            rows.append(form.cleaned_data)
        if len(rows)<self.minimum: raise forms.ValidationError('Дор хаяж %s мөр оруулна уу.' % self.minimum)
        if len(rows)>self.maximum: raise forms.ValidationError('Хамгийн ихдээ %s мөр оруулна уу.' % self.maximum)
        return rows
