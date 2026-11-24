import json
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate1 import Gate1Form,initial_brief,save_brief
from .models import Food,Gate1,PackagingType,Supplier,Ingredient,RecipeLine
from .test_gate0_pricing import FormNestingParser


class Gate1PackagingTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('packaging-editor')
        self.client.force_login(self.user)
        PackagingType.objects.create(code='box',name='Existing box')
        self.food=Food.objects.create(name='Packaging example',owner=self.user,stage='gate1',packaging=100)
        supplier=Supplier.objects.create(name='Supplier')
        ingredient=Ingredient.objects.create(name='Ingredient',supplier=supplier,unit='kg',price=1000)
        RecipeLine.objects.create(food=self.food,ingredient=ingredient,quantity='.1',yield_factor=1,unit_price=1000)
        self.url='/food/%s/'%self.food.pk
        self.complete={'taster_count':'5','tasting_score':'4','capacity_equipment_fit':'Line A','capacity_units_day':'500','capacity_constraint':'no','packaging_label_concept':'box','material_certificate':'no','qa_requirements_issued':'yes','process_flow_ccp_issued':'yes','fridge_check_72h':'pass','tested_in_actual_packaging':'yes','fridge_check_date':'2026-11-24'}

    def test_section_numbering_dropdowns_file_and_removed_old_type(self):
        response=self.client.get(self.url);html=response.content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-packaging"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Савлагаа</legend>',group)
        self.assertEqual(group.count('class="required-star"'),2)
        self.assertNotIn('Савлагааны төрөл',html)
        self.assertEqual(html.count('id="id_packaging_label_concept"'),1)
        self.assertEqual(html.count('id="file-G1-F7"'),1)
        self.assertIn('id="file-G1-F7"',group)
        for number in range(1,8): self.assertIn('class="field-number">5.%s</span>'%number,group)
        for name in ('pack_material','pack_size'):
            field=response.context['gate1form'][name]
            self.assertIn('<select',str(field));self.assertIn('__add_option__',str(field))
        self.assertIn('id="gate1-packaging-cost"',html)
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)

    def test_unit_price_updates_canonical_packaging_cost_and_cogs(self):
        response=self.client.post(self.url,{'action':'gate1_save',**self.complete,'packaging_unit_price':'250.50',
            'packaging_supplier':'Packaging supplier','packaging_moq':'100.5','packaging_lead_days':'7'})
        self.assertEqual(response.status_code,302)
        self.food.refresh_from_db()
        self.assertEqual(self.food.packaging,Decimal('250.50'))
        self.assertEqual(self.food.unit_cost,Decimal('350.50'))
        gate=Gate1.objects.get(development=self.food)
        self.assertEqual(gate.estimated_cogs_vs_limit,Decimal('350.50'))
        self.assertEqual(gate.packaging_supplier,'Packaging supplier')
        self.assertEqual(gate.packaging_moq,Decimal('100.5'))
        self.assertEqual(gate.packaging_lead_days,7)
        page=self.client.get(self.url)
        self.assertEqual(Decimal(page.context['gate1form'].initial['packaging_unit_price']),Decimal('250.50'))
        self.assertContains(page,'value="250.50"')
        self.assertEqual(self.client.post(self.url,{'action':'gate1_save','packaging_unit_price':''}).status_code,302)
        self.food.refresh_from_db();self.assertEqual(self.food.packaging,0)

    def test_required_fields_optional_new_details_and_shared_dropdown_values(self):
        self.assertTrue(Gate1Form(self.complete,food=self.food,submission=True).is_valid())
        for key in ('packaging_label_concept','material_certificate'):
            data={**self.complete,key:''}
            self.assertTrue(Gate1Form(data,food=self.food).is_valid())
            form=Gate1Form(data,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
            self.food.review_status='draft';self.food.save();save_brief(self.food,data)
            self.client.post(self.url,{'action':'submit'})
            self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
            self.food.review_status='manager';self.food.save()
            self.client.post(self.url,{'action':'approve'})
            self.food.refresh_from_db();self.assertEqual(self.food.stage,'gate1')
        self.food.review_status='draft';self.food.save()
        values={'pack_material':'Paper','pack_size':'150 ml','packaging_label_concept':'New cup'}
        for field,label in values.items():
            response=self.client.post('/api/dropdown-options/',json.dumps({'stage':'gate1','field':field,'food':self.food.pk,'label':label}),content_type='application/json')
            self.assertEqual(response.status_code,201)
        form=Gate1Form({**self.complete,**values},food=self.food,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        save_brief(self.food,form.cleaned_data)
        self.assertEqual(initial_brief(self.food)['pack_material'],'Paper')
        for data,key in [({'packaging_unit_price':'-1'},'packaging_unit_price'),({'packaging_lead_days':'-1'},'packaging_lead_days')]:
            form=Gate1Form(data,food=self.food)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)

    def test_existing_material_size_text_and_mockup_history_are_preserved(self):
        save_brief(self.food,{'pack_material':'Legacy material','pack_size':'Legacy size'})
        form=Gate1Form(initial=initial_brief(self.food),food=self.food)
        self.assertFalse(form.legacy_values)
        self.assertIn(('Legacy material','Legacy material'),form.fields['pack_material'].choices)
        self.assertIn(('Legacy size','Legacy size'),form.fields['pack_size'].choices)
        self.assertEqual(self.client.post(self.url,{'action':'slot_upload','slot':'G1-F7','slot_file':SimpleUploadedFile('mockup.pdf',b'mockup')}).status_code,302)
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-packaging"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('mockup.pdf',group)
