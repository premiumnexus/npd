from django.contrib import admin
from .models import Food, Supplier, Ingredient, RecipeLine, Activity
from .forms import LABELS
for model,singular,plural in [
    (Food,'Бүтээгдэхүүн','Бүтээгдэхүүнүүд'),
    (Supplier,'Нийлүүлэгч','Нийлүүлэгчид'),
    (Ingredient,'Орц','Орц'),
    (RecipeLine,'Жорын орц','Жорын орц'),
    (Activity,'Үйл ажиллагаа','Үйл ажиллагаа'),
]:
    model._meta.verbose_name = singular
    model._meta.verbose_name_plural = plural
    for field in model._meta.fields:
        field.verbose_name = LABELS.get(field.name,{
            'food':'Бүтээгдэхүүн','stage':'Үе шат','updated':'Шинэчилсэн огноо',
            'unit_price':'Хадгалсан нэгжийн үнэ','actor':'Хэрэглэгч',
            'text':'Тэмдэглэл','created':'Үүсгэсэн огноо',
        }.get(field.name,field.verbose_name))
admin.site.register([Food,Supplier,Ingredient,RecipeLine,Activity])
admin.site.site_header = 'CU Food удирдлагын самбар'
admin.site.site_title = 'CU Food удирдлага'
admin.site.index_title = 'Бүртгэл ба тохиргоо'
