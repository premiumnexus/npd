from django.contrib import admin
from django.utils import timezone
from .models import Food, Supplier, Ingredient, RecipeLine, Activity, GateAccess, Gate0, Gate1, Gate2, Gate3, Gate0Option, PackagingType, COGSComparisonPolicy, LaunchCheckpoint, GateTransition
from .forms import LABELS
from .models import TargetCostingSettings
from .models import Gate0File
from .models import (
    GateDataArchive, Gate0ImprovementReason, Gate0Daypart, Gate0Allergen,
    Gate0HighRiskInput, Gate0Competitor, Gate0AnalogSKU, Gate0Cannibalisation,
    Gate1Material, Gate3LessonTag,
)
@admin.register(TargetCostingSettings)
class TargetCostingSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):
        return not TargetCostingSettings.objects.exists() and super().has_add_permission(request)

@admin.register(Gate0File)
class Gate0FileAdmin(admin.ModelAdmin):
    list_display=['id','development','slot_code','original_filename','uploader','uploaded_at']
    list_filter=['slot_code']
    search_fields=['original_filename','development__name','=development__id']
    list_select_related=['development','uploader']
    readonly_fields=[field.name for field in Gate0File._meta.fields]
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
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


class OrderedGateInline(admin.TabularInline):
    extra = 0
    ordering = ['position', 'pk']


class Gate0ImprovementReasonInline(OrderedGateInline):
    model = Gate0ImprovementReason
    fields = ['position', 'value']


class Gate0DaypartInline(OrderedGateInline):
    model = Gate0Daypart
    fields = ['position', 'value']


class Gate0AllergenInline(OrderedGateInline):
    model = Gate0Allergen
    fields = ['position', 'value']


class Gate0HighRiskInputInline(OrderedGateInline):
    model = Gate0HighRiskInput
    fields = ['position', 'value']


class Gate0CompetitorInline(OrderedGateInline):
    model = Gate0Competitor
    fields = ['position', 'product', 'price', 'weight_g']


class Gate0AnalogSKUInline(OrderedGateInline):
    model = Gate0AnalogSKU
    fields = ['position', 'sku', 'units_per_store_day']


class Gate0CannibalisationInline(OrderedGateInline):
    model = Gate0Cannibalisation
    fields = ['position', 'sku', 'sales_taken_percent']


class Gate1MaterialInline(OrderedGateInline):
    model = Gate1Material
    fields = ['position', 'material', 'spec_written', 'price_kg', 'moq', 'second_source']


class Gate3LessonTagInline(OrderedGateInline):
    model = Gate3LessonTag
    fields = ['position', 'value']


class GateRecordAdmin(admin.ModelAdmin):
    list_display = ['development_id_display', 'development_name']
    list_select_related = ['development']
    list_filter = ['development__stage', 'development__review_status']
    search_fields = ['development__name', 'development__category']
    raw_id_fields = ['development']
    ordering = ['development_id']

    @admin.display(description='Development ID', ordering='development_id')
    def development_id_display(self, obj):
        return obj.development_id

    @admin.display(description='Бүтээгдэхүүн', ordering='development__name')
    def development_name(self, obj):
        return obj.development.name

    def get_readonly_fields(self, request, obj=None):
        return ['development'] if obj is not None else []

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        GateDataArchive.objects.filter(
            gate=obj._meta.model_name, development_id=obj.development_id,
            reviewed_at__isnull=True,
        ).update(reviewed_at=timezone.now())

    def get_search_results(self, request, queryset, search_term):
        filtered, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.strip().isdecimal() and int(search_term.strip()) <= 9223372036854775807:
            filtered = filtered | queryset.filter(development_id=int(search_term.strip()))
        return filtered, use_distinct


@admin.register(Gate0)
class Gate0Admin(GateRecordAdmin):
    list_display = ['development_id_display', 'product_name', 'category', 'planned_launch_date']
    search_fields = GateRecordAdmin.search_fields + ['product_name', 'category']
    inlines = [
        Gate0ImprovementReasonInline, Gate0DaypartInline, Gate0AllergenInline,
        Gate0HighRiskInputInline, Gate0CompetitorInline, Gate0AnalogSKUInline,
        Gate0CannibalisationInline,
    ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Inline formsets save independently; updating the summary must not replace them.
        development = obj.development
        development.name = (obj.product_name or 'Нэргүй бүтээгдэхүүн')[:160]
        development.category = (obj.category or '')[:80]
        development.save(update_fields=['name', 'category', 'updated'])


@admin.register(Gate1)
class Gate1Admin(GateRecordAdmin):
    list_display = ['development_id_display', 'development_name', 'recipe_version_internal_tasting', 'cogs_status']
    inlines = [Gate1MaterialInline]


@admin.register(Gate2)
class Gate2Admin(GateRecordAdmin):
    list_display = ['development_id_display', 'development_name', 'final_recipe_version', 'cogs_status', 'launch_date']


@admin.register(Gate3)
class Gate3Admin(GateRecordAdmin):
    list_display = ['development_id_display', 'development_name', 'sales_vs_target', 'complaints', 'root_cause']
    inlines = [Gate3LessonTagInline]


@admin.register(GateDataArchive)
class GateDataArchiveAdmin(admin.ModelAdmin):
    list_display = ['gate', 'development_id', 'source_pk', 'issues_summary', 'archived_at', 'reviewed_at']
    list_filter = ['gate']
    search_fields = ['issues']
    actions = None
    readonly_fields = [field.name for field in GateDataArchive._meta.fields]

    @admin.display(description='Conversion issues')
    def issues_summary(self, obj):
        return obj.issues if len(obj.issues) <= 140 else obj.issues[:137] + '...'

    def get_search_results(self, request, queryset, search_term):
        filtered, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term.strip().isdecimal() and int(search_term.strip()) <= 9223372036854775807:
            number = int(search_term.strip())
            filtered = filtered | queryset.filter(development_id=number) | queryset.filter(source_pk=number)
        return filtered, use_distinct

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


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
