import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate0 import Gate0Form,initial_brief,save_brief
from .test_gate0_pricing import FormNestingParser
from .tests import valid_gate0
from .models import Food


class Gate0SalesTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('sales-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Sales example',owner=self.user)

    def test_duplicate_day45_apsd_field_removed_from_creation_and_detail(self):
        self.assertNotIn('day45_success_criteria',Gate0Form().fields)
        for url in ['/food/new/','/food/%s/'%self.food.pk]:
            response=self.client.get(url)
            self.assertNotContains(response,'name="day45_success_criteria"')
            self.assertContains(response,'name="target_units_store_day"')

    def test_gate2_uses_apsd_4_2_with_fallback_for_historical_records(self):
        from .gate2_typed import gate0_targets
        for current,legacy,expected in [('15','99','15'),('0','99','0'),(None,'12','12')]:
            with self.subTest(current=current):
                save_brief(self.food,{'target_units_store_day':current,'day45_success_criteria':legacy})
                self.assertEqual(Decimal(gate0_targets(self.food)['day45_units_store_day']),Decimal(expected))

    def test_section_order_numbers_required_star_and_inline_upload_forms(self):
        for url in ['/food/new/','/food/%s/'%self.food.pk]:
            with self.subTest(url=url):
                response=self.client.get(url)
                html=response.content.decode()
                group=html.split('<fieldset class="gate0-identity gate0-sales"',1)[1].split('</fieldset>',1)[0]
                self.assertIn('<legend>Борлуулалтын зорилт</legend>',group)
                self.assertIn('<small><em>Хэр зарагдах вэ?</em></small>',group)
                self.assertEqual(group.count('class="required-star"'),1)
                self.assertNotIn('id="file-G0-F4"',html)
                self.assertIn('name="analog_skus_sales_target-0-file"',group)
                self.assertIn('name="analog_skus_sales_target-__prefix__-file"',group)
                self.assertNotIn('class="gate0-file-slots"',html)
                self.assertLess(html.index('<legend>Үнэ ба ашиг</legend>'),html.index('<legend>Борлуулалтын зорилт</legend>'))
                form=response.context['form'] if url=='/food/new/' else response.context['gate0form']
                positions=[]
                for index,key in enumerate(Gate0Form.sales_keys,1):
                    self.assertEqual(form.fields[key].gate_number,f'4.{index}')
                    self.assertEqual(form.fields[key].gate_required,key=='target_units_store_day')
                    positions.append(group.index('for="id_%s"'%key))
                self.assertEqual(positions,sorted(positions))
                self.assertEqual(form.fields['analog_skus_sales_target'].label,'Жишиг SKU')
                parser=FormNestingParser();parser.feed(html)
                self.assertFalse(parser.nested)
                self.assertNotIn('form="gate0-analog-upload"',group)

    def test_sku_files_stay_with_their_rows_during_edit_delete_and_replacement(self):
        from .models import Gate0File
        prefix='analog_skus_sales_target'
        response=self.client.post('/food/new/',{
            prefix+'-TOTAL_FORMS':'2',prefix+'-0-sku':'A',prefix+'-1-sku':'B',
            prefix+'-0-file':SimpleUploadedFile('a.pdf',b'File A'),
            prefix+'-1-file':SimpleUploadedFile('b.pdf',b'File B')})
        self.assertEqual(response.status_code,302)
        food=Food.objects.exclude(pk=self.food.pk).get()
        url=response.url
        rows=initial_brief(food)[prefix]
        first,second=[row['attachment'] for row in rows]
        self.assertNotEqual(first,second)
        for attachment in (first,second):
            self.assertEqual(Gate0File.objects.get(pk=attachment).slot_code,'G0-F4')
        edit={'action':'gate0_save',prefix+'-TOTAL_FORMS':'2',
              prefix+'-0-sku':'Renamed A',prefix+'-1-sku':'B',
              prefix+'-0-attachment':first,prefix+'-1-attachment':second}
        self.assertEqual(self.client.post(url,edit).status_code,302)
        rows=initial_brief(food)[prefix]
        self.assertEqual([(row['sku'],row['attachment']) for row in rows],[('Renamed A',first),('B',second)])
        edit[prefix+'-0-DELETE']='1'
        self.assertEqual(self.client.post(url,edit).status_code,302)
        rows=initial_brief(food)[prefix]
        self.assertEqual([(row['sku'],row['attachment']) for row in rows],[('B',second)])
        self.assertEqual(self.client.post(url,{'action':'gate0_save',prefix+'-TOTAL_FORMS':'1',
            prefix+'-0-sku':'B',prefix+'-0-attachment':second,
            prefix+'-0-file':SimpleUploadedFile('updated-b.pdf',b'Updated B')}).status_code,302)
        attachment=initial_brief(food)[prefix][0]['attachment']
        self.assertNotEqual(attachment,second)
        self.assertTrue(Gate0File.objects.filter(pk=first).exists())
        self.assertTrue(Gate0File.objects.filter(pk=second).exists())
        food.review_status='manager';food.save()
        html=self.client.get(url).content.decode()
        self.assertIn('updated-b.pdf',html)
        self.assertIn('a.pdf',html)
        self.assertIn('b.pdf',html)
        download=self.client.get('/gate0/files/%s/'%attachment)
        self.assertEqual(b''.join(download.streaming_content),b'Updated B')
        self.assertEqual(self.client.post(url,{'action':'gate0_save',prefix+'-TOTAL_FORMS':'0'}).status_code,403)

    def test_sku_attachment_validation_rejects_foreign_wrong_slot_and_invalid_ids(self):
        from .gate0 import save_slot_file
        other=Food.objects.create(name='Other',owner=self.user)
        foreign=save_slot_file(other,self.user,'G0-F4',SimpleUploadedFile('other.pdf',b'other'))
        wrong_slot=save_slot_file(self.food,self.user,'G0-F2',SimpleUploadedFile('benchmark.pdf',b'benchmark'))
        for attachment in (foreign.pk,wrong_slot.pk,'invalid'):
            with self.subTest(attachment=attachment):
                response=self.client.post('/food/%s/'%self.food.pk,{'action':'gate0_save',
                    'analog_skus_sales_target-TOTAL_FORMS':'1','analog_skus_sales_target-0-sku':'A',
                    'analog_skus_sales_target-0-attachment':attachment})
                self.assertEqual(response.status_code,200)
                self.assertIn('analog_skus_sales_target',response.context['gate0form'].errors)

    def test_apsd_required_before_submit_and_approval_but_drafts_remain_partial(self):
        complete={key:value for key,value in valid_gate0().items() if key in Gate0Form.required_keys}
        incomplete={**complete,'target_units_store_day':''}
        self.assertTrue(Gate0Form(incomplete).is_valid())
        validation=Gate0Form(incomplete,submission=True)
        self.assertFalse(validation.is_valid())
        self.assertIn('target_units_store_day',validation.errors)
        save_brief(self.food,incomplete)
        url='/food/%s/'%self.food.pk
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'draft')
        self.food.review_status='manager';self.food.save()
        self.client.post(url,{'action':'approve'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.stage,'gate0')
        self.food.review_status='draft';self.food.save()
        form=Gate0Form(complete,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        save_brief(self.food,form.cleaned_data)
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'manager')

    def test_margin_is_calculated_saved_and_copied_to_gate2_ignoring_posted_output(self):
        from .gate2_typed import gate0_targets
        for writeoff,expected in [('5','26.4'),('0','31.4'),('50','-18.6')]:
            with self.subTest(writeoff=writeoff):
                form=Gate0Form({'cu_margin':'30','vendor_rebate':'2','day45_writeoff_percent':writeoff,'day45_margin_percent':'999'})
                self.assertTrue(form.is_valid(),form.errors)
                self.assertTrue(form.fields['day45_margin_percent'].disabled)
                self.assertEqual(form.cleaned_data['day45_margin_percent'],Decimal(expected))
                save_brief(self.food,form.cleaned_data)
                saved=initial_brief(self.food)
                self.assertEqual(Decimal(saved['day45_margin_percent']),Decimal(expected))
                self.assertEqual(Decimal(gate0_targets(self.food)['day45_margin_percent']),Decimal(expected))
        for data in [{},{'cu_margin':'30','vendor_rebate':'2'},{'day45_writeoff_percent':'5'}]:
            form=Gate0Form(data)
            self.assertTrue(form.is_valid(),form.errors)
            self.assertIsNone(form.cleaned_data['day45_margin_percent'])
            self.assertEqual(form.initial['day45_margin_percent'],'')
        form=Gate0Form({'cu_margin':'30.1','vendor_rebate':'2.55','day45_writeoff_percent':'5'})
        self.assertTrue(form.is_valid(),form.errors)
        save_brief(self.food,form.cleaned_data)
        from .models import Gate0
        self.assertEqual(Gate0.objects.get(development=self.food).day45_margin_percent,Decimal('26.88'))

    def test_inline_sku_upload_preserves_history_and_readonly_download_links(self):
        response=self.client.post('/food/new/',{'G0-F4':SimpleUploadedFile('sku.pdf',b'original')})
        self.assertEqual(response.status_code,302)
        food=Food.objects.exclude(pk=self.food.pk).get()
        url=response.url
        self.assertEqual(food.gate0_files.get().slot_code,'G0-F4')
        self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G0-F4',
            'slot_file':SimpleUploadedFile('updated.pdf',b'updated')}).status_code,302)
        food.review_status='manager';food.save()
        html=self.client.get(url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate0-sales"',1)[1].split('</fieldset>',1)[0]
        for record in food.gate0_files.all():
            self.assertIn(record.original_filename,group)
            self.assertIn(record.download_url,group)
        self.assertNotIn('id="file-G0-F4"',group)
