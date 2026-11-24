from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .gate1 import Gate1Form,initial_brief,save_brief
from .models import Food,Gate0,Gate1,Supplier,Ingredient,RecipeLine
from .test_gate0_pricing import FormNestingParser
from .test_gate1_tasting import RequiredStarParser


class Gate1ProductionTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('production-editor')
        self.client.force_login(self.user)
        from .models import PackagingType
        PackagingType.objects.get_or_create(code='test-pack',defaults={'name':'Test packaging'})
        self.food=Food.objects.create(name='Production example',owner=self.user,stage='gate1')
        supplier=Supplier.objects.create(name='Supplier')
        ingredient=Ingredient.objects.create(name='Ingredient',supplier=supplier,unit='kg',price=1000)
        RecipeLine.objects.create(food=self.food,ingredient=ingredient,quantity='.1',yield_factor=1,unit_price=1000)
        self.url='/food/%s/'%self.food.pk
        self.complete={'taster_count':'5','tasting_score':'4','capacity_equipment_fit':'Line A','capacity_units_day':'500','capacity_constraint':'no','packaging_label_concept':'test-pack','material_certificate':'yes','qa_requirements_issued':'yes','process_flow_ccp_issued':'yes','fridge_check_72h':'pass','tested_in_actual_packaging':'yes','fridge_check_date':'2026-11-24'}

    def test_section_order_labels_numbers_and_conditional_stars(self):
        for constraint,visible,hidden in [('no',3,1),('yes',4,0)]:
            save_brief(self.food,{**self.complete,'capacity_constraint':constraint})
            html=self.client.get(self.url).content.decode()
            group=html.split('<fieldset class="gate0-identity gate1-production"',1)[1].split('</fieldset>',1)[0]
            self.assertIn('<legend>Үйлдвэрлэл</legend>',group)
            self.assertIn('<small><em>Үйлдвэрт хийж чадах уу?</em></small>',group)
            self.assertLess(html.index('<legend>Түүхий эд</legend>'),html.index('<legend>Үйлдвэрлэл</legend>'))
            positions=[group.index('class="field-number">4.%s</span>'%index) for index in range(1,5)]
            self.assertEqual(positions,sorted(positions))
            for key in Gate1Form.production_keys:
                self.assertEqual(html.count('id="id_%s"'%key),1)
            self.assertIn('Gate 0 5.7-оос',group)
            self.assertIn('Хязгаарлалт байгаа эсэх',group)
            self.assertNotIn('__add_option__',group)
            stars=RequiredStarParser();stars.feed(group)
            self.assertEqual((stars.visible,stars.hidden),(visible,hidden))
            forms=FormNestingParser();forms.feed(html);self.assertFalse(forms.nested)

    def test_gate0_capacity_prefill_is_editable_and_requires_saving_to_confirm(self):
        Gate0.objects.create(development=self.food,capacity_units_day=600)
        unconfirmed={key:value for key,value in self.complete.items() if key!='capacity_units_day'}
        save_brief(self.food,unconfirmed)
        saved=initial_brief(self.food)
        form=Gate1Form(initial=saved,food=self.food)
        self.assertEqual(form.initial['capacity_units_day'],Decimal(600))
        self.assertFalse(form.fields['capacity_units_day'].disabled)
        validation=Gate1Form(saved,initial=saved,food=self.food,submission=True)
        self.assertFalse(validation.is_valid());self.assertIn('capacity_units_day',validation.errors)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
        response=self.client.post(self.url,{'action':'gate1_save',**self.complete,'capacity_units_day':'750'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Gate1.objects.get(development=self.food).capacity_units_day,Decimal(750))
        Gate0.objects.filter(development=self.food).update(capacity_units_day=900)
        form=Gate1Form(initial=initial_brief(self.food),food=self.food)
        self.assertEqual(Decimal(form.initial['capacity_units_day']),Decimal(750))
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'manager')
        Gate1.objects.filter(development=self.food).update(capacity_units_day=0)
        form=Gate1Form(initial=initial_brief(self.food),food=self.food)
        self.assertEqual(Decimal(form.initial['capacity_units_day']),Decimal(0))

    def test_required_fields_and_yes_only_details_block_submit_and_approval(self):
        self.assertTrue(Gate1Form(self.complete,food=self.food,submission=True).is_valid())
        self.assertTrue(Gate1Form({},food=self.food).is_valid())
        complete={**self.complete,'capacity_constraint':'yes','constraint_details':'Cooling bottleneck'}
        self.assertTrue(Gate1Form(complete,food=self.food,submission=True).is_valid())
        for key in Gate1Form.production_keys:
            with self.subTest(field=key):
                incomplete={**complete,key:''}
                form=Gate1Form(incomplete,food=self.food,submission=True)
                self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
                self.food.review_status='draft';self.food.save()
                save_brief(self.food,incomplete)
                self.client.post(self.url,{'action':'submit'})
                self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
                self.food.review_status='manager';self.food.save()
                self.client.post(self.url,{'action':'approve'})
                self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate1')
        form=Gate1Form({**self.complete,'capacity_constraint':'unexpected'},food=self.food)
        self.assertFalse(form.is_valid());self.assertIn('capacity_constraint',form.errors)

    def test_old_constraint_category_is_preserved_in_description_for_review(self):
        form=Gate1Form(initial={'capacity_constraint':'cooling','constraint_details':'Needs a bigger fridge'},food=self.food)
        self.assertEqual(form.initial['capacity_constraint'],'yes')
        self.assertIn('Хөргөлт',form.initial['constraint_details'])
        self.assertIn('Needs a bigger fridge',form.initial['constraint_details'])
        self.assertTrue(form.fields['constraint_details'].gate_required)
