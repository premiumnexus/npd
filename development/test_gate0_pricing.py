import tempfile
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate0 import Gate0Form,file_slots,save_brief
from .models import Food,Gate0File
from .tests import valid_gate0


class FormNestingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth=0
        self.nested=False

    def handle_starttag(self,tag,attrs):
        if tag=='form':
            self.nested=self.nested or self.depth>0
            self.depth+=1

    def handle_endtag(self,tag):
        if tag=='form': self.depth-=1


class Gate0PricingTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('pricing-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Pricing example',owner=self.user)

    def test_section_numbering_stars_inline_file_and_valid_forms(self):
        for url in ['/food/new/','/food/%s/'%self.food.pk]:
            with self.subTest(url=url):
                response=self.client.get(url)
                html=response.content.decode()
                group=html.split('<fieldset class="gate0-identity gate0-pricing"',1)[1].split('</fieldset>',1)[0]
                self.assertIn('<legend>Үнэ ба ашиг</legend>',group)
                self.assertIn('<small><em>Зөв үнээр хийж чадах уу?</em></small>',group)
                self.assertEqual(group.count('class="required-star"'),4)
                self.assertNotIn('id="file-G0-F2"',html)
                self.assertIn('name="competitor_benchmark-0-file"',group)
                self.assertIn('name="competitor_benchmark-__prefix__-file"',group)
                self.assertNotIn('class="gate0-file-slots"',html)
                self.assertLess(html.index('<legend>Хэрэглэгч ба нотолгоо</legend>'),html.index('<legend>Үнэ ба ашиг</legend>'))
                form=response.context['form'] if url=='/food/new/' else response.context['gate0form']
                positions=[]
                for index,key in enumerate(Gate0Form.pricing_keys,1):
                    self.assertEqual(form.fields[key].gate_number,f'3.{index}')
                    self.assertEqual(form.fields[key].gate_required,key in ('target_shelf_price','cu_margin','vendor_rebate','vendor_margin'))
                    positions.append(group.index('for="id_%s"'%key))
                self.assertEqual(positions,sorted(positions))
                parser=FormNestingParser();parser.feed(html)
                self.assertFalse(parser.nested)
                self.assertNotIn('form="gate0-benchmark-upload"',group)
                self.assertNotIn('name="G0-F1"',html)
                self.assertNotIn('name="G0-F3"',html)
        slot=next(slot for slot in file_slots(self.food) if slot['key']=='G0-F2')
        self.assertTrue(slot['inline'])
        self.assertEqual(slot['number'],'3.1')

    def test_benchmark_files_stay_with_rows_during_edits_removal_and_replacement(self):
        from .gate0 import initial_brief
        prefix='competitor_benchmark'
        response=self.client.post('/food/new/',{
            prefix+'-TOTAL_FORMS':'2',prefix+'-0-product':'A',prefix+'-1-product':'B',
            prefix+'-0-file':SimpleUploadedFile('a.jpg',b'Image A'),
            prefix+'-1-file':SimpleUploadedFile('b.pdf',b'Report B')})
        self.assertEqual(response.status_code,302)
        food=Food.objects.exclude(pk=self.food.pk).get()
        url=response.url
        first,second=[row['attachment'] for row in initial_brief(food)[prefix]]
        self.assertNotEqual(first,second)
        self.assertEqual(set(food.gate0_files.values_list('slot_code',flat=True)),{'G0-F2'})
        edit={'action':'gate0_save',prefix+'-TOTAL_FORMS':'2',
            prefix+'-0-product':'Renamed A',prefix+'-1-product':'B',
            prefix+'-0-attachment':first,prefix+'-1-attachment':second}
        self.assertEqual(self.client.post(url,edit).status_code,302)
        self.assertEqual([(row['product'],row['attachment']) for row in initial_brief(food)[prefix]],[('Renamed A',first),('B',second)])
        edit[prefix+'-0-DELETE']='1'
        self.assertEqual(self.client.post(url,edit).status_code,302)
        self.assertEqual([(row['product'],row['attachment']) for row in initial_brief(food)[prefix]],[('B',second)])
        self.assertEqual(self.client.post(url,{'action':'gate0_save',prefix+'-TOTAL_FORMS':'1',
            prefix+'-0-product':'B',prefix+'-0-attachment':second,
            prefix+'-0-file':SimpleUploadedFile('updated.pdf',b'Updated B')}).status_code,302)
        replacement=initial_brief(food)[prefix][0]['attachment']
        self.assertNotEqual(replacement,second)
        self.assertTrue(Gate0File.objects.filter(pk=first).exists())
        self.assertTrue(Gate0File.objects.filter(pk=second).exists())
        food.review_status='manager';food.save()
        html=self.client.get(url).content.decode()
        for filename in ['a.jpg','b.pdf','updated.pdf']: self.assertIn(filename,html)
        download=self.client.get('/gate0/files/%s/'%replacement)
        self.assertEqual(b''.join(download.streaming_content),b'Updated B')
        self.assertEqual(self.client.post(url,{'action':'gate0_save',prefix+'-TOTAL_FORMS':'0'}).status_code,403)

    def test_competitor_attachment_ids_are_validated_against_product_and_slot(self):
        from .gate0 import save_slot_file
        other=Food.objects.create(name='Other',owner=self.user)
        foreign=save_slot_file(other,self.user,'G0-F2',SimpleUploadedFile('other.pdf',b'other'))
        wrong_slot=save_slot_file(self.food,self.user,'G0-F1',SimpleUploadedFile('evidence.pdf',b'evidence'))
        for attachment in (foreign.pk,wrong_slot.pk,'invalid'):
            response=self.client.post('/food/%s/'%self.food.pk,{'action':'gate0_save',
                'competitor_benchmark-TOTAL_FORMS':'1','competitor_benchmark-0-attachment':attachment})
            self.assertEqual(response.status_code,200)
            self.assertIn('competitor_benchmark',response.context['gate0form'].errors)

    def test_required_pricing_inputs_block_submit_and_approval_but_zero_rebate_is_valid(self):
        complete={key:value for key,value in valid_gate0().items() if key in Gate0Form.required_keys}
        complete['vendor_rebate']='0'
        self.assertTrue(Gate0Form(complete,submission=True).is_valid())
        url='/food/%s/'%self.food.pk
        for key in ('target_shelf_price','cu_margin','vendor_rebate','vendor_margin'):
            with self.subTest(field=key):
                incomplete={**complete,key:''}
                self.assertTrue(Gate0Form(incomplete).is_valid())
                form=Gate0Form(incomplete,submission=True)
                self.assertFalse(form.is_valid())
                self.assertIn(key,form.errors)
                self.food.review_status='draft';self.food.save()
                save_brief(self.food,incomplete)
                self.client.post(url,{'action':'submit'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.review_status,'draft')
                self.food.review_status='manager';self.food.save()
                self.client.post(url,{'action':'approve'})
                self.food.refresh_from_db()
                self.assertEqual(self.food.stage,'gate0')
        self.food.review_status='draft';self.food.save()
        save_brief(self.food,complete)
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status,'manager')

    def test_inline_benchmark_upload_and_history_on_creation_and_edit(self):
        response=self.client.post('/food/new/',{'G0-F2':SimpleUploadedFile('benchmark.pdf',b'original')})
        self.assertEqual(response.status_code,302)
        food=Food.objects.exclude(pk=self.food.pk).get()
        url=response.url
        self.assertEqual(food.gate0_files.get().slot_code,'G0-F2')
        self.assertEqual(self.client.post(url,{'action':'slot_upload','slot':'G0-F2',
            'slot_file':SimpleUploadedFile('updated.pdf',b'updated')}).status_code,302)
        html=self.client.get(url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate0-pricing"',1)[1].split('</fieldset>',1)[0]
        for record in Gate0File.objects.filter(development=food):
            self.assertIn(record.original_filename,group)
            self.assertIn(record.download_url,group)
        food.review_status='manager';food.save()
        html=self.client.get(url).content.decode()
        self.assertNotIn('id="file-G0-F2"',html)
        self.assertIn('benchmark.pdf',html)
