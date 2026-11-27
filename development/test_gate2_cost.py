import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate2 import initial_brief,save_brief,save_slot_file
from .gate2_typed import Gate2Form,derived_values
from .models import Food,Gate0,Gate2,Supplier,Ingredient,RecipeLine,COGSComparisonPolicy
from .test_gate2_mass_trial import COMPLETE
from .test_gate0_pricing import FormNestingParser


class Gate2CostTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name);override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('gate2-cost-editor');self.client.force_login(self.user)
        self.food=Food.objects.create(name='Final cost',owner=self.user,stage='gate2')
        supplier=Supplier.objects.create(name='Supplier')
        ingredient=Ingredient.objects.create(name='Ingredient',supplier=supplier,unit='kg',price=1000)
        self.line=RecipeLine.objects.create(food=self.food,ingredient=ingredient,quantity='.1',yield_factor=1,unit_price=1000)
        Gate0.objects.create(development=self.food,target_shelf_price=1100,cu_margin=0,vendor_rebate=0,vendor_margin=0)
        self.url='/food/%s/'%self.food.pk
        save_slot_file(self.food,self.user,'G2-F5',SimpleUploadedFile('signed.pdf',b'signed transfer'))
        for slot in ('G2-F3','G2-F6','G2-F7','G2-F8'): save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'lab and safety'))

    def quote(self): return save_slot_file(self.food,self.user,'G2-F2',SimpleUploadedFile('quote.pdf',b'Final supplier quote'))

    def test_layout_numbers_quote_required_and_removed_controls(self):
        response=self.client.get(self.url);html=response.content.decode()
        self.assertEqual(response.status_code,200)
        group=html.split('<fieldset class="gate0-identity gate2-cost"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Эцсийн өртөг ба ашиг</legend>',group)
        self.assertIn('<small><em>Эцсийн үнээр ашигтай юу?</em></small>',group)
        self.assertIn('2.4 · Эцсийн COGS',group)
        self.assertIn('2.5 · Gate 0 COGS хязгаар',group)
        self.assertEqual(group.count('class="required-star"'),2)
        for key,number in [('recipe_change_reason','2.2'),('vendor_invoice_price','2.7'),('front_margin_percent','2.8'),('margin_gap_points','2.9'),('implied_vendor_margin_percent','2.10'),('invoice_price_status','2.11'),('overall_cost_status','2.12')]:
            self.assertEqual(response.context['gate2form'].fields[key].gate_number,number)
            self.assertEqual(html.count('id="id_%s"'%key),1)
        self.assertIn('class="field-number">2.13</span>',group)
        self.assertEqual(html.count('id="file-G2-F2"'),1)
        self.assertNotIn('id="file-G2-F11"',html)
        self.assertNotIn('name="final_recipe_version"',html)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_invoice_thresholds_and_worst_of_two_statuses(self):
        for invoice,status in [('1000','Green'),('1050','Amber'),('1050.01','Red')]:
            with self.subTest(invoice=invoice):
                values=derived_values(self.food,None,None,invoice)
                self.assertEqual(values['cogs_status'],'Green')
                self.assertEqual(values['invoice_price_status'],status)
                self.assertEqual(values['overall_cost_status'],status)
        COGSComparisonPolicy.objects.update_or_create(pk=1,defaults={'amber_band_percent':10})
        self.assertEqual(derived_values(self.food,None,None,'1100')['invoice_price_status'],'Amber')
        self.assertEqual(derived_values(self.food,None,None,'1100.01')['invoice_price_status'],'Red')
        self.line.unit_price=12000;self.line.save()
        values=derived_values(self.food,None,None,'1000')
        self.assertEqual(values['cogs_status'],'Red')
        self.assertEqual(values['invoice_price_status'],'Green')
        self.assertEqual(values['overall_cost_status'],'Red')
        self.assertEqual(derived_values(self.food,None,None,None)['overall_cost_status'],'Red')

    def test_invoice_and_quote_required_for_submission_and_approval(self):
        self.assertTrue(Gate2Form({},food=self.food).is_valid())
        save_brief(self.food,{**COMPLETE,'vendor_invoice_price':'1000'})
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
        self.food.review_status='manager';self.food.save()
        self.client.post(self.url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual((self.food.stage,self.food.review_status),('gate2','manager'))
        self.food.review_status='draft';self.food.save()
        self.quote()
        save_brief(self.food,{**COMPLETE,'vendor_invoice_price':None})
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
        self.food.review_status='manager';self.food.save()
        self.client.post(self.url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual((self.food.stage,self.food.review_status),('gate2','manager'))
        self.food.review_status='draft';self.food.save()
        form=Gate2Form({**COMPLETE,'vendor_invoice_price':'1100','overall_cost_status':'Green','invoice_price_status':'Green','recipe_change_reason':'New ingredient'},food=self.food,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['overall_cost_status'],'Red')
        save_brief(self.food,form.cleaned_data)
        self.assertEqual(Gate2.objects.get(development=self.food).recipe_change_reason,'New ingredient')
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')
        self.client.post(self.url,{'action':'qa_accept'})
        self.client.post(self.url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'director')
        self.client.post(self.url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual(self.food.stage,'launch')

    def test_quote_history_and_retired_excel_upload(self):
        first=self.quote();self.quote()
        self.assertEqual(self.client.post(self.url,{'action':'slot_upload','slot':'G2-F11','slot_file':SimpleUploadedFile('old.xlsx',b'old')}).status_code,403)
        group=self.client.get(self.url).content.decode().split('<fieldset class="gate0-identity gate2-cost"',1)[1].split('</fieldset>',1)[0]
        self.assertIn(first.download_url,group)
        response=self.client.get(first.download_url)
        self.assertEqual(b''.join(response.streaming_content),b'Final supplier quote')
        self.assertEqual(initial_brief(self.food)['overall_cost_status'],'Pending')
