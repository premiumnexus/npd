import tempfile
from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate1 import Gate1Form,initial_brief,save_brief,save_slot_file
from .models import Food,Supplier,Ingredient,RecipeLine,Gate1File,Gate1Trial
from .test_gate0_pricing import FormNestingParser


class TrialControlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('name','').startswith('trial_log-'):
            self.controls.append(attrs)


class Gate1RecipeSectionTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('recipe-editor')
        self.client.force_login(self.user)
        from .models import PackagingType
        PackagingType.objects.get_or_create(code='test-pack',defaults={'name':'Test packaging'})
        self.food=Food.objects.create(name='Recipe example',owner=self.user,stage='gate1')
        self.url='/food/%s/'%self.food.pk
        self.supplier=Supplier.objects.create(name='Supplier')
        self.ingredient=Ingredient.objects.create(name='Ingredient',supplier=self.supplier,unit='kg',price=2500)

    def test_section_layout_numbers_file_position_and_form_ownership(self):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        html=response.content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-recipe"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Жор ба өртөг</legend>',group)
        self.assertIn('<small><em>Зорилтот өртөгт багтаж байна уу?</em></small>',group)
        self.assertIn('1.4 · Жорын орц',group)
        self.assertEqual(group.count('class="required-star"'),1)
        self.assertIn('1.6 · Тооцоолсон COGS = орц + савлагаа',group)
        self.assertIn('1.7 · Gate 0 COGS хязгаар (Gate 0 3.10-аас)',group)
        self.assertIn('1.8 · COGS зөрүү',group)
        self.assertIn('1.9 · COGS төлөв',group)
        self.assertIn('id="file-G1-F3"',group)
        self.assertEqual(html.count('id="file-G1-F3"'),1)
        self.assertIn('class="field-number">1.13</span>',group)
        self.assertLess(group.index('id="id_cogs_action"'),group.index('id="file-G1-F3"'))
        parser=FormNestingParser();parser.feed(html)
        self.assertFalse(parser.nested)
        controls=TrialControlParser();controls.feed(group)
        self.assertTrue(controls.controls)
        self.assertTrue(all(control.get('form')=='gate1-brief-form' for control in controls.controls),[control for control in controls.controls if control.get('form')!='gate1-brief-form'])
        self.assertIn('id="gate1-brief-form"',html)
        self.assertIn('name="trial_log-__prefix__-file"',group)

    def test_trial_rows_with_files_save_edit_remove_and_download(self):
        payload={'action':'gate1_save','trial_log-TOTAL_FORMS':'2',
            'trial_log-0-number':'1','trial_log-0-date':'2026-11-24','trial_log-0-changes':'Less salt',
            'trial_log-0-result':'Better','trial_log-0-tasting_score':'4.5','trial_log-0-cogs':'1000',
            'trial_log-0-decision':'continue','trial_log-0-lessons':'Keep testing',
            'trial_log-0-file':SimpleUploadedFile('trial-1.pdf',b'first'),
            'trial_log-1-number':'2','trial_log-1-date':'2026-11-25','trial_log-1-decision':'approved',
            'trial_log-1-file':SimpleUploadedFile('trial-2.pdf',b'second'),
            'typed_cogs':'1200','typed_cogs_reason':'Supplier estimate'}
        self.assertEqual(self.client.post(self.url,payload).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(saved['typed_cogs_reason'],'Supplier estimate')
        self.assertEqual([row['decision'] for row in saved['trial_log']],['continue','approved'])
        first,second=[row['attachment'] for row in saved['trial_log']]
        self.assertNotEqual(first,second)
        self.assertEqual(Gate1Trial.objects.filter(gate=self.food.pk).count(),2)
        html=self.client.get(self.url).content.decode()
        self.assertIn('/gate1/files/%s/'%first,html)
        download=self.client.get('/gate1/files/%s/'%second)
        self.assertEqual(b''.join(download.streaming_content),b'second')
        edited={'action':'gate1_save','trial_log-TOTAL_FORMS':'2','trial_log-0-DELETE':'1',
            'trial_log-1-number':'2','trial_log-1-decision':'approved','trial_log-1-attachment':second}
        self.assertEqual(self.client.post(self.url,edited).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual(len(saved['trial_log']),1)
        self.assertEqual(saved['trial_log'][0]['attachment'],second)
        self.assertTrue(Gate1File.objects.filter(pk=first).exists())
        self.food.review_status='manager';self.food.save()
        self.assertEqual(self.client.post(self.url,edited).status_code,403)
        self.assertIn('trial-2.pdf',self.client.get(self.url).content.decode())

    def test_trial_validation_and_foreign_attachment_rejection(self):
        for row in [{'date':'2026-02-30'},{'tasting_score':'6'},{'cogs':'-1'},{'decision':'unknown'}]:
            form=Gate1Form({'trial_log':[row]},food=self.food)
            self.assertFalse(form.is_valid())
            self.assertIn('trial_log',form.errors)
        other=Food.objects.create(name='Other',owner=self.user,stage='gate1')
        foreign=save_slot_file(other,self.user,'G1-F1',SimpleUploadedFile('other.pdf',b'other'))
        form=Gate1Form({'trial_log':[{'attachment':foreign.pk}]},food=self.food)
        self.assertFalse(form.is_valid())
        self.assertIn('trial_log',form.errors)
        self.assertTrue(Gate1Form({'trial_log':[{'changes':'Partial draft'}]},food=self.food).is_valid())

    def test_recipe_required_for_submission_and_approval_with_catalog_price_and_packaging(self):
        tasting={'taster_count':'5','tasting_score':'4','capacity_equipment_fit':'Line A','capacity_units_day':'500','capacity_constraint':'no','packaging_label_concept':'test-pack','material_certificate':'yes','qa_requirements_issued':'yes','process_flow_ccp_issued':'yes','fridge_check_72h':'pass','tested_in_actual_packaging':'yes','fridge_check_date':'2026-11-24'}
        self.assertTrue(Gate1Form({},food=self.food).is_valid())
        self.assertFalse(Gate1Form(tasting,food=self.food,submission=True).is_valid())
        save_brief(self.food,{'typed_cogs':'1000',**tasting})
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
        self.assertEqual(self.client.post(self.url,{'action':'gate1_line_add','ingredient':self.ingredient.pk,
            'net_grams':'100','yield_factor':'.8'}).status_code,302)
        self.assertEqual(self.food.lines.get().unit_price,Decimal(2500))
        self.client.post(self.url,{'action':'gate1_packaging_save','packaging':'100'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.unit_cost,Decimal('412.5'))
        self.assertTrue(Gate1Form(tasting,food=self.food,submission=True).is_valid())
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'manager')
        self.food.lines.all().delete()
        self.client.post(self.url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate1')
        RecipeLine.objects.create(food=self.food,ingredient=self.ingredient,quantity=0,yield_factor=1,unit_price=2500)
        self.assertFalse(Gate1Form(tasting,food=self.food,submission=True).is_valid())
        self.food.lines.update(quantity=Decimal('.1'))
        self.client.post(self.url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate2')
