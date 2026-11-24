import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate1 import Gate1Form,save_brief,file_slots
from .models import Food,Gate0,PackagingType,Supplier,Ingredient,RecipeLine
from .test_gate0_pricing import FormNestingParser


class Gate1SafetySectionTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('storage-safety-editor')
        self.client.force_login(self.user)
        PackagingType.objects.create(code='box',name='Box')
        self.food=Food.objects.create(name='Safety example',owner=self.user,stage='gate1')
        supplier=Supplier.objects.create(name='Supplier')
        ingredient=Ingredient.objects.create(name='Ingredient',supplier=supplier,unit='kg',price=1000)
        RecipeLine.objects.create(food=self.food,ingredient=ingredient,quantity='.1',yield_factor=1,unit_price=1000)
        self.url='/food/%s/'%self.food.pk
        self.complete={'taster_count':'5','tasting_score':'4','capacity_equipment_fit':'Line A',
            'capacity_units_day':'500','capacity_constraint':'no','packaging_label_concept':'box',
            'material_certificate':'yes','qa_requirements_issued':'yes','process_flow_ccp_issued':'yes',
            'fridge_check_72h':'pass','tested_in_actual_packaging':'yes','fridge_check_date':'2026-11-24'}

    def test_safety_uploads_are_excluded_from_bottom_even_without_inline_flags(self):
        slots=file_slots(self.food)
        for slot in slots:
            if slot['key'] in ('G1-F5','G1-F6'): slot['inline']=False
        with patch('development.views.gate1_file_slots',return_value=slots):
            html=self.client.get(self.url).content.decode()
        safety=html.split('<fieldset class="gate0-identity gate1-safety"',1)[1].split('</fieldset>',1)[0]
        bottom=html.split('<section class="gate0-file-slots"',1)[-1] if '<section class="gate0-file-slots"' in html else ''
        for key,number in [('G1-F5','6.6'),('G1-F6','6.10')]:
            self.assertEqual(html.count('id="file-%s"'%key),1)
            self.assertIn('id="file-%s"'%key,safety)
            self.assertIn('class="field-number">%s</span>'%number,safety)
            self.assertNotIn('id="file-%s"'%key,bottom)

    def test_section_layout_numbers_required_stars_and_adjacent_gate0_reference(self):
        Gate0.objects.create(development=self.food,shelf_life_hours=36)
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-safety"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Хүнсний аюулгүй байдал ба хадгалалт</legend>',group)
        self.assertIn('<small><em>Аюулгүй, хугацаандаа хадгалагдах уу?</em></small>',group)
        self.assertLess(html.index('<legend>Савлагаа</legend>'),html.index('<legend>Хүнсний аюулгүй байдал ба хадгалалт</legend>'))
        self.assertEqual(group.count('class="required-star"'),5)
        positions=[group.index('class="field-number">6.%s</span>'%number) for number in range(1,11)]
        self.assertEqual(positions,sorted(positions))
        self.assertIn('Бодит савлагаанд шалгасан эсэх',group)
        self.assertIn('Gate 0 6.3 · Хадгалах хугацаа (цаг)',group)
        self.assertIn('data-shelf-life-hours>36</strong>',group)
        self.assertNotIn('name="shelf_life_hours"',group)
        for key in ('G1-F5','G1-F6'):
            self.assertEqual(html.count('id="file-%s"'%key),1)
            self.assertIn('id="file-%s"'%key,group)
            self.assertNotIn('id="file-%s"'%key,html.split('<section class="gate0-file-slots"',1)[-1] if '<section class="gate0-file-slots"' in html else '')
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_five_required_fields_block_submission_and_approval_while_drafts_remain_partial(self):
        self.assertTrue(Gate1Form(self.complete,food=self.food,submission=True).is_valid())
        for key in Gate1Form.safety_keys[:5]:
            with self.subTest(field=key):
                incomplete={**self.complete,key:''}
                self.assertTrue(Gate1Form(incomplete,food=self.food).is_valid())
                form=Gate1Form(incomplete,food=self.food,submission=True)
                self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
                self.food.review_status='draft';self.food.save();save_brief(self.food,incomplete)
                self.client.post(self.url,{'action':'submit'})
                self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
                self.food.review_status='manager';self.food.save()
                self.client.post(self.url,{'action':'approve'})
                self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate1')
        self.food.review_status='draft';self.food.save();save_brief(self.food,self.complete)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'manager')

    def test_source_hours_remain_authoritative_and_optional_test_dates_validate(self):
        form=Gate1Form(food=self.food)
        self.assertIsNone(form.gate0_shelf_life_hours)
        gate0=Gate0.objects.create(development=self.food,shelf_life_days=2)
        self.assertEqual(form.gate0_shelf_life_hours,48)
        gate0.shelf_life_hours=72;gate0.save()
        self.assertEqual(form.gate0_shelf_life_hours,72)
        valid=Gate1Form({**self.complete,'shelf_life_test_plan':'Lab','shelf_life_test_days':'3',
            'shelf_life_result_due':'2026-12-01','shelf_life_hours':'999'},food=self.food,submission=True)
        self.assertTrue(valid.is_valid(),valid.errors)
        save_brief(self.food,valid.cleaned_data)
        gate0.refresh_from_db();self.assertEqual(gate0.shelf_life_hours,72)
        for key,value in [('fridge_check_date','2026-02-30'),('shelf_life_test_days','0'),('shelf_life_result_due','invalid')]:
            form=Gate1Form({**self.complete,key:value},food=self.food)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)

    def test_relocated_file_histories_and_readonly_downloads(self):
        for slot in ('G1-F5','G1-F6'):
            for version in range(2):
                self.assertEqual(self.client.post(self.url,{'action':'slot_upload','slot':slot,
                    'slot_file':SimpleUploadedFile('%s-%s.pdf'%(slot,version),b'safety evidence')}).status_code,302)
        self.food.review_status='manager';self.food.save()
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-safety"',1)[1].split('</fieldset>',1)[0]
        for item in self.food.gate1_files.all():
            self.assertIn(item.original_filename,group)
            self.assertIn(item.download_url,group)
            response=self.client.get(item.download_url)
            self.assertEqual(b''.join(response.streaming_content),b'safety evidence')
        self.assertNotIn('name="slot_file"',group)
