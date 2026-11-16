"""Relational gate records linked by the permanent development ID.

The field declarations are deliberately static: the schema must not depend on
form construction, runtime dropdown choices, or database contents.
"""
from decimal import Decimal
from pathlib import PurePosixPath
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def gate1_marketing_upload_path(instance, filename):
    suffix = PurePosixPath(filename).suffix[:20]
    return 'activities/%s/%s%s' % (instance.development_id, uuid.uuid4().hex, suffix)


def gate2_quality_upload_path(instance, filename):
    suffix = PurePosixPath(filename).suffix[:20]
    return 'activities/%s/%s%s' % (instance.development_id, uuid.uuid4().hex, suffix)


class GateRecord(models.Model):
    development = models.OneToOneField(
        'development.Food', on_delete=models.CASCADE, primary_key=True,
        db_column='development_id', related_name='%(class)s_record',
    )

    class Meta:
        abstract = True

    def __str__(self):
        return '%s / %s' % (self._meta.verbose_name, self.development_id)


class Gate0(GateRecord):
    product_type = models.CharField('Шинэ эсвэл сайжруулалт', null=True, blank=True, max_length=200)
    existing_sku = models.TextField('Одоо байгаа SKU код', null=True, blank=True)
    product_name = models.CharField('Бүтээгдэхүүний нэр', null=True, blank=True, max_length=160)
    category = models.CharField('Ангилал', null=True, blank=True, max_length=200)
    subcategory = models.CharField('Дэд ангилал', null=True, blank=True, max_length=200)
    improvement_reason = models.TextField('Юу өөрчлөх, яагаад өөрчлөх тайлбар', null=True, blank=True)
    product_role = models.CharField('Бүтээгдэхүүний үүрэг', null=True, blank=True, max_length=200)
    customer_segment = models.CharField('Зорилтот хэрэглэгчийн сегмент', null=True, blank=True, max_length=200)
    target_customer_occasion = models.TextField('Зорилтот хэрэглэгч, хэрэглээний тайлбар', null=True, blank=True)
    customer_need_evidence = models.TextField('Хэрэглээний нотолгоо', null=True, blank=True)
    evidence_level = models.CharField('Нотолгооны төрөл', null=True, blank=True, max_length=200)
    evidence_reference = models.TextField('Нотолгооны эх сурвалж', null=True, blank=True)
    target_shelf_price = models.BigIntegerField('Зорилтот тавиурын үнэ (НӨАТ-тай, ₮)', null=True, blank=True, validators=[MinValueValidator(1)])
    cu_margin = models.DecimalField('CU-ийн ашгийн хувь', null=True, blank=True, max_digits=14, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(60)])
    vendor_rebate = models.DecimalField('Rebate (буцаан олголт) %', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(30)])
    producer = models.CharField('Үйлдвэрлэгч', null=True, blank=True, max_length=200)
    vendor_margin = models.DecimalField('Нийлүүлэгчийн ашгийн хувь', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(60)])
    vat_percent = models.DecimalField('VAT / НӨАТ (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    price_excl_vat = models.DecimalField('НӨАТ-гүй үнэ (₮)', null=True, blank=True, max_digits=40, decimal_places=18)
    max_invoice_price = models.DecimalField('Нийлүүлэгчийн нэхэмжлэхийн дээд үнэ (₮)', null=True, blank=True, max_digits=40, decimal_places=18)
    cogs_limit = models.DecimalField('COGS-ийн дээд хязгаар (₮)', null=True, blank=True, max_digits=40, decimal_places=18)
    cu_total_margin = models.DecimalField('Rebate орсон CU нийт ашгийн хувь (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    target_units_store_day = models.DecimalField('Зорилтот APSD (ширхэг / дэлгүүр / өдөр)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    store_scope = models.CharField('Дэлгүүрийн хамрах хүрээ', null=True, blank=True, max_length=200)
    store_cluster = models.CharField('Дэлгүүрийн кластер', null=True, blank=True, max_length=200)
    store_count = models.BigIntegerField('Дэлгүүрийн тоо', null=True, blank=True, validators=[MinValueValidator(1)])
    raw_materials_supply_risk = models.CharField('Шинэ түүхий эд байгаа эсэх', null=True, blank=True, max_length=200)
    new_supplier = models.CharField('Шинэ нийлүүлэгч байгаа эсэх', null=True, blank=True, max_length=200)
    seasonal_price_swing = models.CharField('Улирлын үнийн хэлбэлзэл байгаа эсэх', null=True, blank=True, max_length=200)
    moq = models.DecimalField('Захиалгын доод хэмжээ (MOQ)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    first_capacity_check = models.CharField('Хүчин чадлын анхны үнэлгээ', null=True, blank=True, max_length=200)
    capacity_units_day = models.DecimalField('Хүчин чадал (ширхэг / өдөр)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    shelf_life_days = models.BigIntegerField('Хадгалах хугацаа (хоног, шаардлагатай бол)', null=True, blank=True, validators=[MinValueValidator(1)])
    technical_risk_measure = models.TextField('Шинжилгээ, хэмжилтээр шалгах технологийн эрсдэл', null=True, blank=True)
    day45_success_criteria = models.DecimalField('45 хоногийн зорилт (ширхэг / дэлгүүр / өдөр)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    day45_writeoff_percent = models.DecimalField('45 хоногийн акт (өртгийн %)', null=True, blank=True, max_digits=14, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(100)])
    day45_margin_percent = models.DecimalField('45 хоногийн акт-ын дараах ашиг (%)', null=True, blank=True, max_digits=14, decimal_places=2)
    planned_launch_date = models.DateField('Төлөвлөсөн нэвтрүүлэх огноо', null=True, blank=True)

    class Meta:
        db_table = 'development_gate0'
        verbose_name = 'Gate 0'
        verbose_name_plural = 'Gate 0 records'


class Gate1(GateRecord):
    recipe_version_internal_tasting = models.BigIntegerField('Жорын хувилбарын дугаар', null=True, blank=True, validators=[MinValueValidator(1)])
    tasting_score = models.DecimalField('Дотоод амталгааны үнэлгээ (1–5)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(1), MaxValueValidator(5)])
    taster_count = models.BigIntegerField('Амтлагчдын тоо (оруулбал 5-аас доошгүй)', null=True, blank=True, validators=[MinValueValidator(5)])
    consumer_test = models.BigIntegerField('Туршилтанд оролцсон хэрэглэгчдийн тоо', null=True, blank=True, validators=[MinValueValidator(1)])
    consumer_liking = models.DecimalField('Таалагдсан үнэлгээ (1–9)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(1), MaxValueValidator(9)])
    consumer_would_buy_percent = models.DecimalField('Зорилтот үнээр худалдан авах хувь (%)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    typed_cogs = models.DecimalField('COGS гараар оруулах (₮, заавал биш)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    estimated_cogs_vs_limit = models.DecimalField('Тооцоолсон COGS (₮)', null=True, blank=True, max_digits=40, decimal_places=18)
    cogs_limit = models.DecimalField('Gate 0 COGS хязгаар (₮)', null=True, blank=True, max_digits=40, decimal_places=18)
    cogs_status = models.CharField('COGS төлөв', null=True, blank=True, max_length=200)
    cogs_gap_percent = models.DecimalField('COGS зөрүү (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    amber_band = models.DecimalField('Amber босго (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    send_to_director = models.CharField('Merchandising Director руу шилжүүлэх эсэх', null=True, blank=True, max_length=200)
    cogs_source = models.CharField('COGS эх үүсвэр', null=True, blank=True, max_length=200)
    cogs_reason = models.TextField('Amber / Red шалтгаан', null=True, blank=True)
    cogs_action = models.TextField('Amber / Red үед авах арга хэмжээ', null=True, blank=True)
    capacity_equipment_fit = models.TextField('Үйлдвэрлэлийн шугам', null=True, blank=True)
    capacity_units_day = models.DecimalField('Хүчин чадал (ширхэг / өдөр)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    capacity_constraint = models.CharField('Хязгаарлалт', null=True, blank=True, max_length=200)
    constraint_details = models.TextField('Хязгаарлалтын тайлбар', null=True, blank=True)
    fridge_check_72h = models.CharField('72 цаг · Шалгалтын үр дүн', null=True, blank=True, max_length=200)
    fridge_check_date = models.DateField('Шалгасан огноо', null=True, blank=True)
    shelf_life_test_plan = models.TextField('Лаборатори', null=True, blank=True)
    shelf_life_test_days = models.BigIntegerField('Туршилтын хугацаа (хоног)', null=True, blank=True, validators=[MinValueValidator(1)])
    shelf_life_result_due = models.DateField('Үр дүн гарах огноо', null=True, blank=True)
    qa_requirements_issued = models.CharField('Хориглосон орцыг шалгасан эсэх', null=True, blank=True, max_length=200)
    process_flow_ccp_issued = models.CharField('Процессын урсгал ба CCP шаардлага гаргасан эсэх', null=True, blank=True, max_length=200)
    packaging_label_concept = models.CharField('Савлагааны төрөл', null=True, blank=True, max_length=200)
    pack_size = models.TextField('Савлагааны хэмжээ', null=True, blank=True)
    pack_material = models.TextField('Савлагааны материал', null=True, blank=True)
    material_certificate = models.CharField('Материалын гэрчилгээ байгаа эсэх', null=True, blank=True, max_length=200)
    marketing_name = models.TextField('Кампанит ажлын нэр', null=True, blank=True)
    marketing_key_message = models.TextField('Гол мессеж', null=True, blank=True)
    marketing_brief = models.TextField('Нэвтрүүлэлтийн маркетингийн санаа', null=True, blank=True)
    marketing_idea_file = models.FileField(
        'Нэвтрүүлэлтийн маркетингийн санааны файл',
        upload_to=gate1_marketing_upload_path, null=True, blank=True, editable=False,
    )
    marketing_idea_filename = models.CharField(max_length=255, null=True, blank=True, editable=False)
    marketing_idea_uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        null=True, blank=True, editable=False,
    )
    marketing_idea_uploaded_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = 'development_gate1'
        verbose_name = 'Gate 1'
        verbose_name_plural = 'Gate 1 records'


class Gate2(GateRecord):
    mass_trial_result = models.DecimalField('Масс туршилтын багц (кг)', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    trial_yield_percent = models.DecimalField('Туршилтын гарц (%)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    trial_taste_score = models.DecimalField('Амтын үнэлгээ (1–5)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(1), MaxValueValidator(5)])
    trial_date = models.DateField('Туршилтын огноо', null=True, blank=True)
    final_recipe_version = models.BigIntegerField('Эцсийн жорын хувилбар', null=True, blank=True, validators=[MinValueValidator(1)])
    vendor_invoice_price = models.DecimalField('Нийлүүлэгчийн нэхэмжлэхийн үнэ (₮)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    final_cogs_invoice_price = models.DecimalField('Эцсийн COGS (₮, жорын тооцооноос)', null=True, blank=True, max_digits=40, decimal_places=18)
    cogs_limit = models.DecimalField('Gate 0 COGS хязгаар (₮)', null=True, blank=True, max_digits=40, decimal_places=18)
    cogs_status = models.CharField('COGS төлөв', null=True, blank=True, max_length=200)
    cogs_gap_percent = models.DecimalField('COGS зөрүү (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    front_margin_percent = models.DecimalField('Бодит үнээрх CU ашгийн хувь (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    margin_gap_points = models.DecimalField('CU ашгийн зорилтоос дутсан зөрүү (нэгж хувь)', null=True, blank=True, max_digits=40, decimal_places=18)
    implied_vendor_margin_percent = models.DecimalField('Бодит үнээрх нийлүүлэгчийн ашгийн хувь (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    lab_results_approved_shelf_life = models.CharField('Микробиологийн шинжилгээ', null=True, blank=True, max_length=200)
    chemical_lab_result = models.CharField('Химийн шинжилгээ', null=True, blank=True, max_length=200)
    approved_shelf_life_days = models.BigIntegerField('Батлагдсан хадгалах хугацаа (хоног)', null=True, blank=True, validators=[MinValueValidator(1)])
    final_technology_transfer_document = models.TextField('Технологи шилжүүлэх баримтын хувилбар', null=True, blank=True)
    technology_transfer_date = models.DateField('Баримтын огноо', null=True, blank=True)
    label_allergens = models.TextField('Орцын жагсаалтад мэдэгдсэн харшил үүсгэгчид (MNS 6648:2016)', null=True, blank=True)
    label_checked = models.CharField('Шошгыг шалгасан эсэх', null=True, blank=True, max_length=200)
    barcode_system_registration = models.TextField('Баркод', null=True, blank=True)
    sku_code_requested = models.CharField('SKU код хүссэн эсэх', null=True, blank=True, max_length=200)
    pos_name_price_checked = models.CharField('POS нэр, үнийг шалгасан эсэх', null=True, blank=True, max_length=200)
    allocation = models.BigIntegerField('Дэлгүүрийн тоо', null=True, blank=True, validators=[MinValueValidator(0)])
    first_order_units = models.BigIntegerField('Эхний захиалга (ширхэг)', null=True, blank=True, validators=[MinValueValidator(0)])
    supply_readiness = models.CharField('Эхний 2 долоо хоногийн түүхий эд бэлэн эсэх', null=True, blank=True, max_length=200)
    delivery_slot = models.TextField('Хүргэлтийн цагийн хуваарь', null=True, blank=True)
    cold_chain_temperature = models.DecimalField('Хүйтэн хэлхээний температур (°C)', null=True, blank=True, max_digits=6, decimal_places=2)
    marketing_plan = models.TextField('Маркетингийн сувгууд', null=True, blank=True)
    marketing_promotion = models.TextField('Урамшуулал', null=True, blank=True)
    marketing_start_date = models.DateField('Маркетинг эхлэх огноо', null=True, blank=True)
    marketing_end_date = models.DateField('Маркетинг дуусах огноо', null=True, blank=True)
    unit_weight_mean = models.DecimalField('Нэгжийн дундаж жин (г)', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    unit_weight_variation = models.DecimalField('Нэгжийн жингийн хэлбэлзэл (± г)', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    quality_tolerance_baseline = models.DecimalField('Жингийн зорилт (г)', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    quality_weight_min = models.DecimalField('Жингийн доод хязгаар (г)', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    quality_weight_max = models.DecimalField('Жингийн дээд хязгаар (г)', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    quality_standard_file = models.FileField(
        'Чанарын стандарт', upload_to=gate2_quality_upload_path,
        null=True, blank=True, editable=False,
    )
    quality_standard_filename = models.CharField(max_length=255, null=True, blank=True, editable=False)
    quality_standard_uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        null=True, blank=True, editable=False,
    )
    quality_standard_uploaded_at = models.DateTimeField(null=True, blank=True, editable=False)
    day45_target_confirmed = models.CharField('Gate 0-ийн зорилт хэвээр / Өөрчилсөн', null=True, blank=True, max_length=200)
    day45_units_store_day = models.DecimalField('45 хоногийн зорилт (ширхэг / дэлгүүр / өдөр)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    day45_writeoff_percent = models.DecimalField('45 хоногийн акт (өртгийн %)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    day45_margin_percent = models.DecimalField('45 хоногийн акт-ын дараах ашиг (%)', null=True, blank=True, max_digits=14, decimal_places=2)
    day45_change_reason = models.TextField('45 хоногийн зорилт өөрчилсөн шалтгаан', null=True, blank=True)
    original_launch_date = models.DateField('Gate 0 (0.22) төлөвлөсөн огноо', null=True, blank=True)
    launch_date = models.DateField('Нэвтрүүлэх огноо', null=True, blank=True)
    launch_delay_days = models.BigIntegerField('Төлөвлөгөөнөөс зөрсөн хоног (+ хойшилсон / − урагшилсан)', null=True, blank=True)
    launch_date_change_reason = models.TextField('Нэвтрүүлэх огноо өөрчилсөн шалтгаан', null=True, blank=True)

    class Meta:
        db_table = 'development_gate2'
        verbose_name = 'Gate 2'
        verbose_name_plural = 'Gate 2 records'


class Gate3(GateRecord):
    planned_vs_actual_launch_date = models.DateField('Gate 0 (0.22) төлөвлөсөн огноо', null=True, blank=True)
    actual_launch_date = models.DateField('Gate 2 (2.12) нэвтрүүлсэн огноо', null=True, blank=True)
    launch_days_late = models.BigIntegerField('Хоцорсон хоног', null=True, blank=True)
    launch_delay_reason = models.TextField('Нэвтрүүлэлт хоцорсон шалтгаан', null=True, blank=True)
    sales_vs_target = models.DecimalField('45 хоногийн борлуулалт (ширхэг / дэлгүүр / өдөр)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    sales_target = models.DecimalField('Gate 0 (0.14) борлуулалтын зорилт', null=True, blank=True, max_digits=40, decimal_places=18)
    sales_difference = models.DecimalField('Борлуулалтын зөрүү (бодит − зорилт)', null=True, blank=True, max_digits=40, decimal_places=18)
    sales_attainment_percent = models.DecimalField('Борлуулалтын зорилтын биелэлт (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    margin_after_writeoff = models.DecimalField('Акт-ын дараах ашиг (%)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MaxValueValidator(100)])
    margin_target = models.DecimalField('Gate 0 (0.21) ашгийн зорилт (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    margin_difference = models.DecimalField('Ашгийн зөрүү (хувийн пункт)', null=True, blank=True, max_digits=40, decimal_places=18)
    writeoff_percent_of_cost = models.DecimalField('акт (өртгийн %)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    writeoff_target = models.DecimalField('Gate 0 (0.21) акт зорилт (%)', null=True, blank=True, max_digits=40, decimal_places=18)
    writeoff_difference = models.DecimalField('акт зөрүү (хувийн пункт)', null=True, blank=True, max_digits=40, decimal_places=18)
    availability = models.DecimalField('Бараагүй байсан дэлгүүр-хоног (%)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    shelf_samples_day7_day14 = models.CharField('Day 7 дээж зөвшөөрөх хүрээнд эсэх', null=True, blank=True, max_length=200)
    day14_sample_within_tolerance = models.CharField('Day 14 дээж зөвшөөрөх хүрээнд эсэх', null=True, blank=True, max_length=200)
    complaints = models.BigIntegerField('Гомдлын тоо', null=True, blank=True, validators=[MinValueValidator(0)])
    complaint_type = models.TextField('Гомдлын төрөл', null=True, blank=True)
    complaints_closed = models.CharField('Гомдлыг хаасан эсэх', null=True, blank=True, max_length=200)
    customer_feedback = models.DecimalField('CSAT үнэлгээ', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    customer_comments = models.TextField('Хэрэглэгчийн гол санал', null=True, blank=True)
    root_cause = models.CharField('Шалтгааны онош', null=True, blank=True, max_length=200)
    root_cause_evidence = models.TextField('Шалтгааны нотолгоо', null=True, blank=True)
    lesson_card = models.TextField('Үргэлжлүүлэх зүйл', null=True, blank=True)
    lesson_stop = models.TextField('Зогсоох зүйл', null=True, blank=True)
    lesson_change = models.TextField('Өөрчлөх зүйл', null=True, blank=True)
    handover_final_cogs = models.CharField('Эцсийн COGS байгаа эсэх', null=True, blank=True, max_length=200)
    handover_technology_document = models.CharField('Технологи шилжүүлэх баримт байгаа эсэх', null=True, blank=True, max_length=200)
    handover_label = models.CharField('Шошго байгаа эсэх', null=True, blank=True, max_length=200)
    handover_marketing_plan = models.CharField('Маркетингийн төлөвлөгөө байгаа эсэх', null=True, blank=True, max_length=200)
    handover_pack_complete = models.CharField('Handover багц бүрэн эсэх', null=True, blank=True, max_length=200)

    class Meta:
        db_table = 'development_gate3'
        verbose_name = 'Gate 3'
        verbose_name_plural = 'Gate 3 records'


class OrderedGateItem(models.Model):
    position = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ['position', 'pk']


class Gate0ImprovementReason(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='improvement_reasons',
    )
    value = models.CharField(max_length=200)

    class Meta:
        db_table = 'development_gate0_improvement_reason'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_improvement_reason_position',
        )]


class Gate0Daypart(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='dayparts',
    )
    value = models.CharField(max_length=200)

    class Meta:
        db_table = 'development_gate0_daypart'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_daypart_position',
        )]


class Gate0Allergen(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='allergens',
    )
    value = models.CharField(max_length=200)

    class Meta:
        db_table = 'development_gate0_allergen'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_allergen_position',
        )]


class Gate0HighRiskInput(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='high_risk_inputs',
    )
    value = models.CharField(max_length=200)

    class Meta:
        db_table = 'development_gate0_high_risk_input'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_high_risk_input_position',
        )]


class Gate3LessonTag(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate3', on_delete=models.CASCADE, db_column='development_id',
        related_name='lesson_tags',
    )
    value = models.CharField(max_length=200)

    class Meta:
        db_table = 'development_gate3_lesson_tag'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate3_lesson_tag_position',
        )]


class Gate0Competitor(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='competitor_benchmark',
    )
    product = models.TextField('Бүтээгдэхүүн', null=True, blank=True)
    price = models.BigIntegerField('Үнэ (₮)', null=True, blank=True, validators=[MinValueValidator(1)])
    weight_g = models.DecimalField('Жин (г)', null=True, blank=True, max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        db_table = 'development_gate0_competitor'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_competitor_position',
        )]


class Gate0AnalogSKU(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='analog_skus_sales_target',
    )
    sku = models.TextField('SKU код', null=True, blank=True)
    units_per_store_day = models.DecimalField('Ширхэг / дэлгүүр / өдөр (бодит)', null=True, blank=True, max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        db_table = 'development_gate0_analog_sku'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_analog_sku_position',
        )]


class Gate0Cannibalisation(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate0', on_delete=models.CASCADE, db_column='development_id',
        related_name='cannibalisation',
    )
    sku = models.TextField('Нөлөөлөх SKU код', null=True, blank=True)
    sales_taken_percent = models.DecimalField('Борлуулалтаас авах хувь (%)', null=True, blank=True, max_digits=4, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        db_table = 'development_gate0_cannibalisation'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate0_cannibalisation_position',
        )]


class Gate1Material(OrderedGateItem):
    gate = models.ForeignKey(
        'Gate1', on_delete=models.CASCADE, db_column='development_id',
        related_name='raw_material_spec_price_moq_second_source',
    )
    material = models.TextField('Шинэ / өөрчлөгдсөн түүхий эд', null=True, blank=True)
    spec_written = models.CharField('Техникийн тодорхойлолт бичигдсэн эсэх', null=True, blank=True, max_length=200)
    price_kg = models.DecimalField('Үнэ (₮ / кг)', null=True, blank=True, max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    moq = models.DecimalField('MOQ', null=True, blank=True, max_digits=14, decimal_places=3, validators=[MinValueValidator(0)])
    second_source = models.CharField('Нийлүүлэлтийн өөр эх үүсвэр байгаа эсэх', null=True, blank=True, max_length=200)

    class Meta:
        db_table = 'development_gate1_material'
        ordering = ['position', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'position'], name='gate1_material_position',
        )]


class GateDataArchive(models.Model):
    """Immutable source payloads, including rows without a surviving parent."""
    gate = models.CharField(max_length=5)
    source_pk = models.BigIntegerField()
    development_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    raw_data = models.TextField()
    issues = models.TextField(blank=True, default='')
    archived_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'development_gate_data_archive'
        ordering = ['gate', 'source_pk']
        constraints = [models.UniqueConstraint(
            fields=['gate', 'source_pk'], name='gate_archive_source',
        )]

    def __str__(self):
        return '%s / %s' % (self.gate, self.source_pk)
