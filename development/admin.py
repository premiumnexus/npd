from django.contrib import admin
from .models import Food, Supplier, Ingredient, RecipeLine, Activity, GateAccess, Gate0Brief, Gate1Brief, Gate2Brief, Gate3Brief, Gate0Option, PackagingType, COGSComparisonPolicy, LaunchCheckpoint, GateTransition
from .forms import LABELS
from .models import TargetCostingSettings
@admin.register(TargetCostingSettings)
class TargetCostingSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):
        return not TargetCostingSettings.objects.exists() and super().has_add_permission(request)
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
admin.site.register(Gate0Brief)
admin.site.register(Gate1Brief)
admin.site.register(Gate2Brief)
admin.site.register(Gate3Brief)
admin.site.register(PackagingType)
admin.site.register(LaunchCheckpoint)
@admin.register(GateTransition)
class GateTransitionAdmin(admin.ModelAdmin):
    list_display=['food','action','from_stage','to_stage','actor','occurred_at']
    list_filter=['to_stage','action']
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
@admin.register(COGSComparisonPolicy)
class COGSComparisonPolicyAdmin(admin.ModelAdmin):
    fields=['amber_band_percent']
    def has_add_permission(self,request):
        return not COGSComparisonPolicy.objects.exists() and super().has_add_permission(request)
@admin.register(Gate0Option)
class Gate0OptionAdmin(admin.ModelAdmin):
    list_display=['kind','code','label','category','active','order']
    list_filter=['kind','category','active']
    search_fields=['code','label']
    list_editable=['label','active','order']
@admin.register(GateAccess)
class GateAccessAdmin(admin.ModelAdmin):
    list_display = ['group','stage','can_edit','can_submit','can_qa_accept','can_manager_decide','can_director_decide']
    list_filter = ['stage','group']
    list_editable = ['can_edit','can_submit','can_qa_accept','can_manager_decide','can_director_decide']
admin.site.site_header = 'CU Food удирдлагын самбар'
admin.site.site_title = 'CU Food удирдлага'
admin.site.index_title = 'Бүртгэл ба тохиргоо'
