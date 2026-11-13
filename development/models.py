from decimal import Decimal
import uuid
from pathlib import PurePosixPath
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

POSITIVE = [MinValueValidator(Decimal('0.001'))]
NONNEGATIVE = [MinValueValidator(0)]
def activity_upload_path(instance,filename):
    return 'activities/%s/%s%s' % (instance.food_id,uuid.uuid4().hex,PurePosixPath(filename).suffix[:20])
STAGES = [('gate0','Gate 0 · Санаа ба танилцуулга'),('gate1','Gate 1 · Концепц ба жор'),('gate2','Gate 2 · Үйлдвэрлэл, нэвтрүүлэлтийн бэлэн байдал'),('launch','Launch GO · 7 / 14 дэх өдрийн хяналт'),('gate3','Gate 3 · 45 дахь өдрийн дүгнэлт')]
from .workflow import SUBMITTERS
ROLES = SUBMITTERS

class TargetCostingSettings(models.Model):
    vat_percent = models.DecimalField('НӨАТ (%)', max_digits=5, decimal_places=2,
        default=Decimal('10.0'), validators=[MinValueValidator(0), MaxValueValidator(100)])
    class Meta:
        verbose_name = 'Gate 0 тооцооны тохиргоо'
        verbose_name_plural = 'Gate 0 тооцооны тохиргоо'
    def __str__(self): return 'VAT: %s%%' % self.vat_percent

class GateAccess(models.Model):
    group = models.ForeignKey('auth.Group',on_delete=models.CASCADE)
    stage = models.CharField('Үе шат',max_length=20,choices=STAGES)
    can_edit = models.BooleanField('Засах',default=False)
    can_submit = models.BooleanField('Хяналтад илгээх',default=False)
    can_qa_accept = models.BooleanField('QA зөвшөөрөл',default=False)
    can_manager_decide = models.BooleanField('Менежерийн шийдвэр',default=False)
    can_director_decide = models.BooleanField('Захирлын шийдвэр',default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['group','stage'],name='unique_gate_group')]
        verbose_name = 'Үе шатны эрх'
        verbose_name_plural = 'Үе шатны эрхүүд'
    def __str__(self): return '%s / %s' % (self.group,self.get_stage_display())

class SharedDropdownOption(models.Model):
    stage = models.CharField(max_length=20)
    field = models.CharField(max_length=120)
    scope = models.CharField(max_length=80, blank=True)
    label = models.CharField(max_length=200)
    label_key = models.CharField(max_length=64)

    class Meta:
        ordering = ['pk']
        constraints = [models.UniqueConstraint(
            fields=['stage', 'field', 'scope', 'label_key'], name='unique_shared_dropdown_option')]

    def __str__(self):
        return self.label


class Supplier(models.Model):
    name = models.CharField(max_length=160,unique=True)
    contact = models.CharField(max_length=200,blank=True)
    def __str__(self): return self.name

class Gate0Option(models.Model):
    kind=models.CharField('Жагсаалт',max_length=30,choices=[(key,label) for key,label in [('subcategory','Дэд ангилал'),('improvement_reason','Сайжруулалтын шалтгаан'),('product_role','Бүтээгдэхүүний үүрэг'),('segment','Хэрэглэгчийн сегмент'),('cluster','Дэлгүүрийн кластер'),('allergen','Харшил үүсгэгч'),('high_risk','Өндөр эрсдэлтэй орц')]])
    code=models.CharField('Код',max_length=80)
    label=models.CharField('Нэр',max_length=200)
    category=models.CharField('Ангилал',max_length=8,blank=True,choices=[('FF','FF'),('ISF','ISF')])
    active=models.BooleanField('Идэвхтэй',default=True)
    order=models.PositiveIntegerField('Дараалал',default=0)
    class Meta:
        ordering=['order','pk']
        constraints=[models.UniqueConstraint(fields=['kind','code','category'],name='unique_gate0_option')]
        verbose_name='Gate 0 сонголт'
        verbose_name_plural='Gate 0 сонголтын жагсаалтууд'
    def __str__(self): return self.label

class Ingredient(models.Model):
    name = models.CharField(max_length=160)
    supplier = models.ForeignKey(Supplier,on_delete=models.PROTECT)
    unit = models.CharField(max_length=8,choices=[('kg','kg'),('L','L'),('each','each')])
    price = models.DecimalField(max_digits=14,decimal_places=2,validators=NONNEGATIVE)
    def __str__(self): return '%s · %s (%s)' % (self.name,self.supplier,self.unit)

class PackagingType(models.Model):
    code=models.CharField('Код',max_length=60,unique=True)
    name=models.CharField('Нэр',max_length=160)
    active=models.BooleanField('Идэвхтэй',default=True)
    class Meta:
        verbose_name='Савлагааны төрөл'
        verbose_name_plural='Савлагааны төрлүүд'
    def __str__(self): return self.name

class COGSComparisonPolicy(models.Model):
    amber_band_percent=models.DecimalField('Amber зөрүүний босго (%)',max_digits=6,decimal_places=2,default=5,validators=NONNEGATIVE)
    id=models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False)
    green_max_percent=models.DecimalField('Green дээд босго (COGS / хязгаар × 100)',max_digits=8,decimal_places=2,null=True,blank=True,validators=NONNEGATIVE)
    amber_max_percent=models.DecimalField('Amber дээд босго (COGS / хязгаар × 100)',max_digits=8,decimal_places=2,null=True,blank=True,validators=NONNEGATIVE)
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.green_max_percent is not None and self.amber_max_percent is not None and self.green_max_percent > self.amber_max_percent:
            raise ValidationError('Green босго Amber босгоос их байж болохгүй.')
    class Meta:
        verbose_name='Gate 1 COGS босго'
        verbose_name_plural='Gate 1 COGS босго'
    def __str__(self): return 'Gate 1 COGS'

class Food(models.Model):
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=80,default='Ready meal')
    brief = models.TextField(blank=True)
    stage = models.CharField(max_length=20,choices=STAGES,default='gate0')
    review_status = models.CharField('Хяналтын төлөв',max_length=20,default='draft',choices=[('draft','Бэлтгэж байна'),('qa','QA зөвшөөрөл хүлээж байна'),('manager','Fresh Food Manager хүлээж байна'),('director','Merchandising Director хүлээж байна')])
    completed = models.BooleanField('Хөгжүүлэлт дууссан',default=False)
    gate0_submitted_at=models.DateTimeField('Gate 0 анх илгээсэн',null=True,blank=True)
    recipe_version=models.PositiveIntegerField('Жорын хувилбар',null=True,blank=True,validators=[MinValueValidator(1)])
    launched_at=models.DateTimeField('Launch GO эхэлсэн огноо',null=True,blank=True)
    gate3_opened_at=models.DateTimeField('Day 45 / Gate 3 нээгдсэн огноо',null=True,blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    due = models.DateField(null=True,blank=True)
    production_date = models.DateField('Planned production date',null=True,blank=True,db_index=True)
    market_launch_date = models.DateField('Actual market launch date',null=True,blank=True,db_index=True)
    batch_units = models.PositiveIntegerField(default=100,validators=[MinValueValidator(1)])
    yield_percent = models.DecimalField(max_digits=5,decimal_places=2,default=100,validators=[MinValueValidator(Decimal('0.01')),MaxValueValidator(100)])
    packaging = models.DecimalField(max_digits=12,decimal_places=2,default=0,validators=NONNEGATIVE)
    labor = models.DecimalField(max_digits=12,decimal_places=2,default=0,validators=NONNEGATIVE)
    overhead = models.DecimalField(max_digits=12,decimal_places=2,default=0,validators=NONNEGATIVE)
    selling_price = models.DecimalField(max_digits=12,decimal_places=2,default=0,validators=NONNEGATIVE)
    updated = models.DateTimeField(auto_now=True)
    @property
    def ingredient_cost(self): return sum((line.cost for line in self.lines.all()),Decimal(0))
    @property
    def effective_units(self): return Decimal(self.batch_units)*self.yield_percent/100
    @property
    def unit_cost(self): return self.ingredient_cost+self.packaging
    @property
    def margin(self): return (self.selling_price-self.unit_cost)/self.selling_price*100 if self.selling_price else 0
    @property
    def role(self): return ROLES.get(self.stage,'Category Manager (MD)')
    @property
    def role_label(self):
        return self.role
    def __str__(self): return self.name

class LaunchCheckpoint(models.Model):
    food=models.ForeignKey(Food,on_delete=models.CASCADE,related_name='launch_checkpoints')
    day=models.PositiveSmallIntegerField('Өдөр',choices=[(7,'Day 7'),(14,'Day 14')])
    checked_date=models.DateField('Шалгасан огноо',null=True,blank=True)
    sample_result=models.CharField('Дээжийн үр дүн',max_length=11,blank=True,choices=[('within','Хязгаарт багтсан'),('conditional','Нөхцөлтэй'),('outside','Хязгаараас гарсан')])
    action_plan=models.TextField('Арга хэмжээ, хариуцагч, хугацаа',blank=True)
    within_tolerance=models.CharField('Зөвшөөрөх хүрээнд байгаа эсэх',max_length=3,blank=True,choices=[('yes','Тийм'),('no','Үгүй')])
    sample_weight=models.DecimalField('Дээжийн жин (г)',max_digits=12,decimal_places=3,null=True,blank=True,validators=NONNEGATIVE)
    sample_texture=models.TextField('Дээжийн бүтэц',blank=True)
    sample_taste=models.TextField('Дээжийн амт',blank=True)
    sample_notes=models.TextField('Дээжийн тэмдэглэл',blank=True)
    sales_snapshot=models.DecimalField('Борлуулалт (ширхэг / дэлгүүр / өдөр)',max_digits=14,decimal_places=2,null=True,blank=True,validators=NONNEGATIVE)
    sales_notes=models.TextField('Борлуулалтын тойм',blank=True)
    complaints_count=models.PositiveIntegerField('Гомдлын тоо',null=True,blank=True)
    complaints_details=models.TextField('Гомдлын мэдээлэл',blank=True)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True)
    recorded_at=models.DateTimeField('Бүртгэсэн огноо',null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['food','day'],name='unique_launch_checkpoint_day')]
        verbose_name='Нэвтрүүлэлтийн хяналтын цэг'
        verbose_name_plural='Нэвтрүүлэлтийн хяналтын цэгүүд'
    def __str__(self): return '%s / Day %s'%(self.food,self.day)

class RecipeLine(models.Model):
    yield_factor=models.DecimalField('Орцын гарц (0.01–1.00)',max_digits=5,decimal_places=4,default=1,validators=[MinValueValidator(Decimal('0.01')),MaxValueValidator(1)])
    food = models.ForeignKey(Food,on_delete=models.CASCADE,related_name='lines')
    ingredient = models.ForeignKey(Ingredient,on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12,decimal_places=3,validators=POSITIVE)
    unit_price = models.DecimalField(max_digits=14,decimal_places=2,validators=NONNEGATIVE)
    @property
    def cost(self): return self.quantity/self.yield_factor*self.unit_price
    @property
    def net_grams(self): return self.quantity*1000

class Activity(models.Model):
    food = models.ForeignKey(Food,on_delete=models.CASCADE,related_name='activities')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True)
    text = models.TextField()
    attachment = models.FileField(upload_to=activity_upload_path,blank=True)
    attachment_name = models.CharField(max_length=255,blank=True)
    attachment_stage = models.CharField(max_length=20,choices=STAGES,blank=True)
    attachment_slot = models.CharField(max_length=8,blank=True,choices=[(key,key) for key in ['G0-F1','G0-F2','G0-F3','G0-F4']+['G1-F%s' % number for number in range(1,11)]+['G2-F%s' % number for number in range(1,14)]+['G3-F%s' % number for number in range(1,4)]+['L%sF%s' % (day,number) for day in [7,14] for number in range(1,9 if day==7 else 11)]])
    created = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created']

class GateTransition(models.Model):
    food=models.ForeignKey(Food,on_delete=models.CASCADE,related_name='gate_transitions')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True)
    activity=models.OneToOneField(Activity,on_delete=models.SET_NULL,null=True,blank=True)
    action=models.CharField('Үйлдэл',max_length=20,choices=[('created','Үүсгэсэн'),('submit','Илгээсэн'),('qa_accept','QA зөвшөөрсөн'),('approve','Баталсан'),('return','Буцаасан'),('escalate','Шатлан шилжүүлсэн'),('auto_open','Day 45 автоматаар нээгдсэн')])
    from_stage=models.CharField(max_length=20,choices=STAGES,blank=True)
    to_stage=models.CharField(max_length=20,choices=STAGES)
    from_review=models.CharField(max_length=20,blank=True)
    to_review=models.CharField(max_length=20,blank=True)
    completed=models.BooleanField(default=False)
    occurred_at=models.DateTimeField('Шилжсэн огноо')
    class Meta:
        ordering=['occurred_at','pk']
        verbose_name='Үе шатны шилжилт'
        verbose_name_plural='Үе шатны шилжилтийн түүх'


from .gate_models import (
    Gate0, Gate1, Gate2, Gate3, GateDataArchive,
    Gate0ImprovementReason, Gate0Daypart, Gate0Allergen, Gate0HighRiskInput,
    Gate3LessonTag, Gate0Competitor, Gate0AnalogSKU, Gate0Cannibalisation, Gate1Material,
)
