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
STAGES = [('concept','Санаа'),('recipe','Жор хөгжүүлэлт'),('sourcing','Нийлүүлэгч сонголт'),('quality','Чанарын хяналт'),('costing','Өртөг батлах'),('approved','Нэвтрүүлэхэд бэлэн')]
ROLES = {'concept':'Product','recipe':'R&D','sourcing':'Procurement','quality':'Quality','costing':'Finance'}

class Supplier(models.Model):
    name = models.CharField(max_length=160,unique=True)
    contact = models.CharField(max_length=200,blank=True)
    def __str__(self): return self.name

class Ingredient(models.Model):
    name = models.CharField(max_length=160)
    supplier = models.ForeignKey(Supplier,on_delete=models.PROTECT)
    unit = models.CharField(max_length=8,choices=[('kg','kg'),('L','L'),('each','each')])
    price = models.DecimalField(max_digits=14,decimal_places=2,validators=NONNEGATIVE)
    def __str__(self): return '%s · %s (%s)' % (self.name,self.supplier,self.unit)

class Food(models.Model):
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=80,default='Ready meal')
    brief = models.TextField(blank=True)
    stage = models.CharField(max_length=20,choices=STAGES,default='concept')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    due = models.DateField()
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
    def unit_cost(self): return self.ingredient_cost/self.effective_units+self.packaging+self.labor+self.overhead
    @property
    def margin(self): return (self.selling_price-self.unit_cost)/self.selling_price*100 if self.selling_price else 0
    @property
    def role(self): return ROLES.get(self.stage,'Product')
    @property
    def role_label(self):
        return {'Product':'Бүтээгдэхүүн','R&D':'Судалгаа, хөгжүүлэлт','Procurement':'Худалдан авалт','Quality':'Чанар','Finance':'Санхүү'}[self.role]
    def __str__(self): return self.name

class RecipeLine(models.Model):
    food = models.ForeignKey(Food,on_delete=models.CASCADE,related_name='lines')
    ingredient = models.ForeignKey(Ingredient,on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12,decimal_places=3,validators=POSITIVE)
    unit_price = models.DecimalField(max_digits=14,decimal_places=2,validators=NONNEGATIVE)
    @property
    def cost(self): return self.quantity*self.unit_price

class Activity(models.Model):
    food = models.ForeignKey(Food,on_delete=models.CASCADE,related_name='activities')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    text = models.TextField()
    attachment = models.FileField(upload_to=activity_upload_path,blank=True)
    attachment_name = models.CharField(max_length=255,blank=True)
    attachment_stage = models.CharField(max_length=20,choices=STAGES,blank=True)
    created = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created']
