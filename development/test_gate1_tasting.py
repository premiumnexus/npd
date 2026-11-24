import tempfile
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate1 import Gate1Form,save_brief
from .models import Food,Supplier,Ingredient,RecipeLine
from .test_gate0_pricing import FormNestingParser


class RequiredStarParser(HTMLParser):
    def __init__(self):
        super().__init__();self.visible=0;self.hidden=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='span' and attrs.get('class')=='required-star':
            if 'hidden' in attrs: self.hidden+=1
            else: self.visible+=1


class Gate1TastingTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('tasting-editor')
        self.client.force_login(self.user)
        from .models import PackagingType
        PackagingType.objects.get_or_create(code='test-pack',defaults={'name':'Test packaging'})
        self.food=Food.objects.create(name='Tasting example',owner=self.user,stage='gate1')
        supplier=Supplier.objects.create(name='Supplier')
        ingredient=Ingredient.objects.create(name='Ingredient',supplier=supplier,unit='kg',price=1000)
        RecipeLine.objects.create(food=self.food,ingredient=ingredient,quantity='.1',yield_factor=1,unit_price=1000)
        self.url='/food/%s/'%self.food.pk

    def test_section_layout_numbering_conditional_stars_and_inline_files(self):
        for consumers,visible,hidden in [('',2,2),('10',4,0)]:
            save_brief(self.food,{'consumer_test':consumers})
            response=self.client.get(self.url)
            html=response.content.decode()
            group=html.split('<fieldset class="gate0-identity gate1-tasting"',1)[1].split('</fieldset>',1)[0]
            self.assertIn('<legend>Амт ба хэрэглэгч</legend>',group)
            self.assertIn('<small><em>Хэрэглэгчдэд таалагдаж байна уу?</em></small>',group)
            self.assertLess(html.index('<legend>Жор ба өртөг</legend>'),html.index('<legend>Амт ба хэрэглэгч</legend>'))
            positions=[group.index('class="field-number">2.%s</span>'%number) for number in range(1,8)]
            self.assertEqual(positions,sorted(positions))
            stars=RequiredStarParser();stars.feed(group)
            self.assertEqual((stars.visible,stars.hidden),(visible,hidden))
            for key in ('G1-F1','G1-F2'):
                self.assertEqual(html.count('id="file-%s"'%key),1)
                self.assertIn('id="file-%s"'%key,group)
                bottom=html.split('<section class="gate0-file-slots"',1)[-1] if '<section class="gate0-file-slots"' in html else ''
                self.assertNotIn('id="file-%s"'%key,bottom)
            parser=FormNestingParser();parser.feed(html)
            self.assertFalse(parser.nested)

    def test_required_fields_and_conditional_requirements_preserve_partial_drafts(self):
        base={'taster_count':'5','tasting_score':'4','capacity_equipment_fit':'Line A','capacity_units_day':'500','capacity_constraint':'no','packaging_label_concept':'test-pack','material_certificate':'yes','qa_requirements_issued':'yes','process_flow_ccp_issued':'yes','fridge_check_72h':'pass','tested_in_actual_packaging':'yes','fridge_check_date':'2026-11-24'}
        self.assertTrue(Gate1Form(base,food=self.food,submission=True).is_valid())
        self.assertTrue(Gate1Form({'consumer_test':'10'},food=self.food).is_valid())
        complete={**base,'consumer_test':'10','consumer_liking':'7','consumer_would_buy_percent':'0'}
        self.assertTrue(Gate1Form(complete,food=self.food,submission=True).is_valid())
        for key in ('taster_count','tasting_score','consumer_liking','consumer_would_buy_percent'):
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
        for data,key in [({**base,'taster_count':'4'},'taster_count'),({**base,'tasting_score':'5.1'},'tasting_score'),({**complete,'consumer_liking':'10'},'consumer_liking'),({**complete,'consumer_would_buy_percent':'101'},'consumer_would_buy_percent')]:
            form=Gate1Form(data,food=self.food,submission=True)
            self.assertFalse(form.is_valid());self.assertIn(key,form.errors)
        self.food.review_status='draft';self.food.save()
        save_brief(self.food,complete)
        self.client.post(self.url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'manager')

    def test_relocated_file_slots_preserve_history_downloads_and_review_locks(self):
        for key in ('G1-F1','G1-F2'):
            for version in range(2):
                response=self.client.post(self.url,{'action':'slot_upload','slot':key,
                    'slot_file':SimpleUploadedFile('%s-%s.pdf'%(key,version),b'file content')})
                self.assertEqual(response.status_code,302)
        self.food.review_status='manager';self.food.save()
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-tasting"',1)[1].split('</fieldset>',1)[0]
        for item in self.food.gate1_files.all():
            self.assertIn(item.original_filename,group)
            self.assertIn(item.download_url,group)
        self.assertNotIn('name="slot_file"',group)
        self.assertEqual(self.client.post(self.url,{'action':'slot_upload','slot':'G1-F1',
            'slot_file':SimpleUploadedFile('blocked.pdf',b'blocked')}).status_code,403)
