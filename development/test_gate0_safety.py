from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase

from .gate0 import Gate0Form,initial_brief,save_brief
from .models import Food,Gate0
from .tests import valid_gate0


class Gate0SafetyTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('safety-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Safety example',owner=self.user)

    def test_section_order_title_subtitle_numbering_and_required_stars(self):
        for url in ['/food/new/','/food/%s/'%self.food.pk]:
            with self.subTest(url=url):
                response=self.client.get(url)
                html=response.content.decode()
                group=html.split('<fieldset class="gate0-identity gate0-safety"',1)[1].split('</fieldset>',1)[0]
                self.assertIn('<legend>Хүнсний аюулгүй байдал</legend>',group)
                self.assertIn('<small><em>Ямар эрсдэлтэй вэ?</em></small>',group)
                self.assertEqual(group.count('class="required-star"'),2)
                self.assertLess(html.index('<legend>Үйлдвэрлэл ба нийлүүлэлт</legend>'),html.index('<legend>Хүнсний аюулгүй байдал</legend>'))
                form=response.context['form'] if url=='/food/new/' else response.context['gate0form']
                positions=[]
                for index,key in enumerate(Gate0Form.safety_keys,1):
                    self.assertEqual(form.fields[key].gate_number,f'6.{index}')
                    self.assertEqual(form.fields[key].gate_required,index<=2)
                    positions.append(group.index('class="field-number">6.%s</span>'%index))
                self.assertEqual(positions,sorted(positions))
                self.assertIn('Хадгалах хугацаа (цаг)',group)
                self.assertNotIn('name="shelf_life_days"',html)

    def test_required_safety_selections_block_progress_and_optional_fields_can_be_blank(self):
        complete={key:value for key,value in valid_gate0().items() if key in Gate0Form.required_keys}
        form=Gate0Form(complete,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        url='/food/%s/'%self.food.pk
        for key in Gate0Form.safety_keys[:2]:
            with self.subTest(field=key):
                incomplete={**complete,key:[]}
                self.assertTrue(Gate0Form(incomplete).is_valid())
                validation=Gate0Form(incomplete,submission=True)
                self.assertFalse(validation.is_valid())
                self.assertIn(key,validation.errors)
                self.food.review_status='draft';self.food.save()
                save_brief(self.food,incomplete)
                self.client.post(url,{'action':'submit'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.review_status,'draft')
                self.food.review_status='manager';self.food.save()
                self.client.post(url,{'action':'approve'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.stage,'gate0')
                self.assertEqual(self.food.review_status,'manager')
        self.food.review_status='draft';self.food.save()
        save_brief(self.food,form.cleaned_data)
        saved=initial_brief(self.food)
        self.assertEqual(saved['first_food_safety_risk'],['milk'])
        self.assertEqual(saved['high_risk_inputs'],['rice'])
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'manager')

    def test_shelf_life_hours_save_without_being_interpreted_as_days(self):
        response=self.client.post('/food/%s/'%self.food.pk,{'action':'gate0_save','shelf_life_hours':'36'})
        self.assertEqual(response.status_code,302)
        record=Gate0.objects.get(development=self.food)
        self.assertEqual(record.shelf_life_hours,36)
        self.assertIsNone(record.shelf_life_days)
        self.assertEqual(initial_brief(self.food)['shelf_life_hours'],36)
        for value in ['0','-1','1.5']:
            form=Gate0Form({'shelf_life_hours':value})
            self.assertFalse(form.is_valid())
            self.assertIn('shelf_life_hours',form.errors)

    def test_existing_day_values_convert_to_hours_without_overwriting_explicit_hours(self):
        save_brief(self.food,{'shelf_life_days':2})
        self.assertEqual(initial_brief(self.food)['shelf_life_hours'],48)
        other=Food.objects.create(name='Hours already entered',owner=self.user)
        save_brief(other,{'shelf_life_days':3,'shelf_life_hours':36})
        migration=import_module('development.migrations.0005_shelf_life_hours')
        migration.copy_shelf_life_hours(apps,SimpleNamespace(connection=connection))
        self.assertEqual(Gate0.objects.get(development=self.food).shelf_life_hours,48)
        self.assertEqual(Gate0.objects.get(development=other).shelf_life_hours,36)
