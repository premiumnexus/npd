from django import forms
from .models import Food, Ingredient, Supplier, RecipeLine
from django.utils import timezone

LABELS = {
    'name':'Нэр','category':'Ангилал','brief':'Товч танилцуулга',
    'owner':'Хариуцагч','due':'Дуусах огноо','batch_units':'Нэг багцын бүтээгдэхүүний тоо',
    'yield_percent':'Гарц (%)','packaging':'Нэгжийн сав баглаа боодлын зардал',
    'labor':'Нэгжийн хөдөлмөрийн зардал','overhead':'Нэгжийн нэмэгдэл зардал',
    'selling_price':'Борлуулах үнэ','contact':'Холбоо барих мэдээлэл',
    'supplier':'Нийлүүлэгч','unit':'Хэмжих нэгж','price':'Нэгжийн үнэ (₮)',
    'ingredient':'Орц','quantity':'Нэг багцад орох хэмжээ',
    'production_date':'Үйлдвэрлэхээр төлөвлөсөн огноо',
    'market_launch_date':'Зах зээлд гарсан бодит огноо',
}

class MongolianModelForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name,field in self.fields.items():
            field.label = LABELS.get(name,field.label)
        if 'unit' in self.fields:
            self.fields['unit'].choices = [('', '---------'),('kg','кг'),('L','л'),('each','ширхэг')]

class LaunchDatesForm(MongolianModelForm):
    class Meta:
        model = Food
        fields = ['production_date','market_launch_date']
        widgets = {field: forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}) for field in fields}
    def clean_market_launch_date(self):
        value = self.cleaned_data.get('market_launch_date')
        if value and value > timezone.localdate():
            raise forms.ValidationError('Зах зээлд гарсан огноо өнөөдөр эсвэл өмнөх өдөр байна.')
        return value

class FoodForm(MongolianModelForm):
    class Meta:
        model = Food
        fields = ['name','category','brief','owner','due','batch_units','yield_percent','packaging','labor','overhead','selling_price']
        widgets = {'due': forms.DateInput(attrs={'type':'date'})}
class SupplierForm(MongolianModelForm):
    class Meta:
        model = Supplier
        fields = ['name','contact']
class IngredientForm(MongolianModelForm):
    class Meta:
        model = Ingredient
        fields = ['name','supplier','unit','price']
class LineForm(MongolianModelForm):
    class Meta:
        model = RecipeLine
        fields = ['ingredient','quantity']

class Gate1LineForm(MongolianModelForm):
    net_grams=forms.DecimalField(min_value=0,max_digits=15,decimal_places=3,required=False)
    class Meta:
        model=RecipeLine
        fields=['ingredient','net_grams','yield_factor','unit_price']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['ingredient'].queryset=Ingredient.objects.filter(unit='kg')
        import json
        self.fields['ingredient'].widget.attrs['data-prices']=json.dumps({str(item.pk):str(item.price) for item in self.fields['ingredient'].queryset})
        from django.urls import reverse
        from .dropdown_widgets import AddableSelect
        ingredient = self.fields['ingredient']
        ingredient.widget = AddableSelect(attrs=ingredient.widget.attrs, choices=ingredient.choices)
        ingredient.widget.attrs.update({'data-options-url': reverse('add_dropdown_option'),
            'data-option-stage': 'gate1', 'data-option-field': 'recipe_ingredient'})
        self.fields['yield_factor'].required=False
        self.fields['unit_price'].required=False
        self.fields['net_grams'].label='Нэг бүтээгдэхүүнд орох цэвэр жин (г)'
        self.fields['unit_price'].label='Түүхий эдийн үнэ (₮ / кг)'
        self.fields['unit_price'].help_text='Хоосон бол орцын сангийн үнийг авна.'
        self.fields['yield_factor'].help_text='0.70 = 70% гарц. Өртөг = цэвэр жин / 1000 / гарц × кг үнэ.'
        if self.instance.pk: self.initial['net_grams']=self.instance.net_grams
        for key in ['net_grams','yield_factor','unit_price']:
            self.fields[key].widget.attrs['class']='costing-input'
    def clean(self):
        from decimal import Decimal,InvalidOperation
        data=super().clean()
        grams=data.get('net_grams')
        # Accept previous clients using kg, while the UI now uses grams.
        if grams is None and self.data.get('quantity') is not None:
            try:
                grams=Decimal(self.data['quantity'])*1000
                if not grams.is_finite() or grams<0: raise InvalidOperation()
            except (InvalidOperation,ValueError,TypeError):
                self.add_error('net_grams','Invalid quantity')
        data['net_grams']=grams
        self.instance.quantity=(grams or Decimal(0))/1000
        if data.get('yield_factor') is None: data['yield_factor']=Decimal(1)
        if data.get('unit_price') is None and data.get('ingredient'):
            data['unit_price']=data['ingredient'].price
        return data

class Gate1PackagingForm(forms.ModelForm):
    class Meta:
        model=Food
        fields=['packaging']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['packaging'].required=False
        self.fields['packaging'].label='Нэгжийн сав баглаа боодлын зардал (₮)'
        self.fields['packaging'].widget.attrs['class']='costing-input'
    def clean_packaging(self):
        from decimal import Decimal
        return self.cleaned_data.get('packaging') or Decimal(0)
