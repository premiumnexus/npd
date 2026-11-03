import getpass
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, User
from django.db import transaction
from development.models import Supplier, Ingredient, Food, RecipeLine, Activity, ROLES

class Command(BaseCommand):
    help = 'Create sample records and a demo administrator (password requested interactively).'
    def add_arguments(self,parser):
        parser.add_argument('--username',default='demo')
    @transaction.atomic
    def handle(self,*args,**options):
        for role in set(ROLES.values()): Group.objects.get_or_create(name=role)
        user,created = User.objects.get_or_create(username=options['username'])
        if created:
            password = getpass.getpass('Choose demo password (at least 10 characters): ')
            if len(password) < 10: raise CommandError('Password must have at least 10 characters')
            user.set_password(password)
            user.is_staff = user.is_superuser = True
            user.first_name, user.last_name = 'Demo','Developer'
            user.save()
        supplier,_ = Supplier.objects.get_or_create(name='Demo · Fresh Foods',defaults={'contact':'Sample supplier — replace before real use'})
        ingredients=[]
        for name,price in [('Chicken thigh',14500),('Short-grain rice',4800),('Teriyaki sauce',12500),('Mixed vegetables',6200)]:
            ingredient,_=Ingredient.objects.get_or_create(name=name,supplier=supplier,defaults={'unit':'kg','price':price})
            ingredients.append(ingredient)
        for index,(name,stage,category) in enumerate([('Teriyaki chicken bowl','recipe','Ready meal'),('Spicy chicken onigiri','sourcing','Onigiri'),('Garden lunch box','quality','Lunch box'),('Chicken rice wrap','costing','Wrap')]):
            food,created=Food.objects.get_or_create(name=name,defaults={'stage':stage,'category':category,'owner':user,'due':date.today()+timedelta(days=7+index*3),'brief':'Sample development for evaluating the CU Food process.','batch_units':100,'yield_percent':95,'packaging':350,'labor':220,'overhead':130,'selling_price':6500})
            if created:
                for ingredient,quantity in zip(ingredients,[12,10,2,5]): RecipeLine.objects.create(food=food,ingredient=ingredient,quantity=Decimal(quantity),unit_price=ingredient.price)
                Activity.objects.create(food=food,actor=user,text='Sample development created. All suppliers and prices are illustrative.')
        self.stdout.write(self.style.SUCCESS('Demo ready. Sign in with '+user.username+' and your chosen password.'))
