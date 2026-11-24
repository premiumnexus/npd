from django import forms

class AttachmentRow(forms.Form):
    attachment_model='Gate0File'
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from django.apps import apps
        attachment_model=apps.get_model('development',self.attachment_model)
        attachment=self.initial.get('attachment')
        try:
            self.existing_attachment=attachment_model.objects.filter(pk=attachment).first() if attachment else None
        except (TypeError,ValueError,OverflowError):
            self.existing_attachment=None


class EvidenceRow(AttachmentRow):
    evidence_keys=('customer_need_evidence','evidence_level','evidence_reference')
    customer_need_evidence=forms.CharField(label='Хэрэглээний нотолгоо',widget=forms.Textarea(attrs={'rows':2}))
    evidence_level=forms.ChoiceField(label='Нотолгооны төрөл',choices=[('', '---------'),('A','A · POS / борлуулалтын өгөгдөл'),('B','B · Хэрэглэгчийн судалгаа'),('C','C · Дэлгүүрийн хүсэлт'),('D','D · Өрсөлдөгчийн үнэ'),('E','E · борлуулалт'),('F','F · Гадаад CU/BGF борлуулалт'),('G','G · Тренд')])
    evidence_reference=forms.CharField(label='Нотолгооны эх сурвалж',widget=forms.Textarea(attrs={'rows':2}))
    file=forms.FileField(label='Хэрэглэгчийн нотолгоо',required=False)
    attachment=forms.IntegerField(min_value=1,required=False,widget=forms.HiddenInput)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from .dropdown_options import apply_options
        # Retain choices previously added to the standalone evidence dropdown.
        apply_options(self,'gate0')
        apply_options(self,'gate0','evidence.')
        self.fields['evidence_level'].widget.attrs.update({
            'data-evidence-level':True,
            'aria-describedby':self['evidence_level'].auto_id+'_reminder',
        })

class CompetitorRow(AttachmentRow):
    product=forms.CharField(label='Бүтээгдэхүүн')
    price=forms.IntegerField(label='Үнэ (₮)',min_value=1)
    weight_g=forms.DecimalField(label='Жин (г)',min_value=0,decimal_places=2,max_digits=12)
    file=forms.FileField(label='Жишиг бүтээгдэхүүний зураг, үнэ',required=False)
    attachment=forms.IntegerField(min_value=1,required=False,widget=forms.HiddenInput)

class AnalogRow(AttachmentRow):
    sku=forms.CharField(label='SKU код')
    units_per_store_day=forms.DecimalField(label='Ширхэг / дэлгүүр / өдөр (бодит)',min_value=0,decimal_places=2,max_digits=12)
    file=forms.FileField(label='Одоогийн SKU-ийн мэдээлэл (борлуулалт, гомдол, акт)',required=False)
    attachment=forms.IntegerField(min_value=1,required=False,widget=forms.HiddenInput)

class CannibalisationRow(forms.Form):
    sku=forms.CharField(label='Нөлөөлөх SKU код')
    sales_taken_percent=forms.DecimalField(label='Борлуулалтаас авах хувь (%)',min_value=0,max_value=100,decimal_places=1,max_digits=4)

class RowsWidget(forms.Widget):
    template_name='widgets/gate0_rows.html'
    needs_multipart_form=True
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
            rows.append({key:(files.get(prefix+key) if isinstance(field,forms.FileField) else data.get(prefix+key,'')) for key,field in self.row_form.base_fields.items()})
        return rows
    def get_context(self,name,value,attrs):
        context=super().get_context(name,value,attrs)
        values=value if isinstance(value,list) else []
        values=values or [{}]
        render_attrs=context['widget']['attrs']
        disabled=bool(render_attrs.get('disabled'))
        def row(data,prefix):
            form=self.row_form(initial=data,prefix=prefix)
            for field in form.fields.values():
                field.required=False
                field.disabled=disabled
                if render_attrs.get('form'): field.widget.attrs['form']=render_attrs['form']
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
            row_files={key:data.get(key) for key,field in self.row_form.base_fields.items() if isinstance(field,forms.FileField)}
            form=self.row_form(data,row_files)
            if not self.complete:
                for field in form.fields.values(): field.required=False
            if not form.is_valid():
                raise forms.ValidationError('%s-р мөр: %s' % (index+1,'; '.join('%s: %s' % (form.fields[key].label,', '.join(errors)) for key,errors in form.errors.items())))
            rows.append(form.cleaned_data)
        if len(rows)<self.minimum: raise forms.ValidationError('Дор хаяж %s мөр оруулна уу.' % self.minimum)
        if len(rows)>self.maximum: raise forms.ValidationError('Хамгийн ихдээ %s мөр оруулна уу.' % self.maximum)
        return rows
