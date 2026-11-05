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
    class Meta:
        model = RecipeLine
        fields = ['ingredient','quantity','unit_price']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['unit_price'].required=False
        self.fields['unit_price'].label='Орцын нэгжийн үнэ (₮)'
        self.fields['quantity'].label='Нэг бүтээгдэхүүнд орох хэмжээ'
        self.fields['quantity'].help_text='Орцын хэмжих нэгжээр оруулна. 100 грамм = 0.1 кг.'
        self.fields['unit_price'].help_text='Хоосон үлдээвэл орцын санд бүртгэсэн үнийг авна.'
    def clean(self):
        data=super().clean()
        if data.get('unit_price') is None and data.get('ingredient'):
            data['unit_price']=data['ingredient'].price
        return data
