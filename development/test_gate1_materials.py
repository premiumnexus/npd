import tempfile
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate1 import initial_brief,save_slot_file
from .models import Food,Gate1File
from .test_gate0_pricing import FormNestingParser


PREFIX='raw_material_spec_price_moq_second_source'


class MaterialControlParser(HTMLParser):
    def __init__(self):
        super().__init__();self.controls=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('name','').startswith(PREFIX+'-'): self.controls.append(attrs)


class Gate1MaterialSectionTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable();self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('material-editor')
        self.client.force_login(self.user)
        self.food=Food.objects.create(name='Materials example',owner=self.user,stage='gate1')
        self.url='/food/%s/'%self.food.pk

    def test_section_layout_number_and_per_row_file_column(self):
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-materials"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('<legend>Түүхий эд</legend>',group)
        self.assertIn('<small><em>Орцыг тогтвортой авч чадах уу?</em></small>',group)
        self.assertIn('class="field-number">3.1</span>',group)
        self.assertIn('Түүхий эдийн техникийн тодорхойлолт',group)
        self.assertIn('name="%s-0-file"'%PREFIX,group)
        self.assertIn('name="%s-__prefix__-file"'%PREFIX,group)
        self.assertNotIn('id="file-G1-F4"',html)
        self.assertNotIn('class="required-star"',group)
        self.assertLess(html.index('<legend>Амт ба хэрэглэгч</legend>'),html.index('<legend>Түүхий эд</legend>'))
        parser=FormNestingParser();parser.feed(html);self.assertFalse(parser.nested)
        controls=MaterialControlParser();controls.feed(group)
        self.assertTrue(controls.controls)
        self.assertTrue(all(control.get('form')=='gate1-brief-form' for control in controls.controls))

    def test_material_files_follow_edits_removal_and_replacement(self):
        payload={'action':'gate1_save',PREFIX+'-TOTAL_FORMS':'2',
            PREFIX+'-0-material':'Material A',PREFIX+'-1-material':'Material B',
            PREFIX+'-0-file':SimpleUploadedFile('a.pdf',b'Specification A'),
            PREFIX+'-1-file':SimpleUploadedFile('b.pdf',b'Specification B')}
        self.assertEqual(self.client.post(self.url,payload).status_code,302)
        first,second=[row['attachment'] for row in initial_brief(self.food)[PREFIX]]
        self.assertNotEqual(first,second)
        self.assertEqual(set(self.food.gate1_files.values_list('slot_code',flat=True)),{'G1-F4'})
        edit={'action':'gate1_save',PREFIX+'-TOTAL_FORMS':'2',
            PREFIX+'-0-material':'Renamed A',PREFIX+'-1-material':'Material B',
            PREFIX+'-0-attachment':first,PREFIX+'-1-attachment':second}
        self.assertEqual(self.client.post(self.url,edit).status_code,302)
        self.assertEqual([(row['material'],row['attachment']) for row in initial_brief(self.food)[PREFIX]],[('Renamed A',first),('Material B',second)])
        edit[PREFIX+'-0-DELETE']='1'
        self.assertEqual(self.client.post(self.url,edit).status_code,302)
        self.assertEqual([(row['material'],row['attachment']) for row in initial_brief(self.food)[PREFIX]],[('Material B',second)])
        self.assertEqual(self.client.post(self.url,{'action':'gate1_save',PREFIX+'-TOTAL_FORMS':'1',
            PREFIX+'-0-material':'Material B',PREFIX+'-0-attachment':second,
            PREFIX+'-0-file':SimpleUploadedFile('updated-b.pdf',b'Updated specification B')}).status_code,302)
        replacement=initial_brief(self.food)[PREFIX][0]['attachment']
        self.assertNotEqual(replacement,second)
        self.assertTrue(Gate1File.objects.filter(pk=first).exists())
        self.assertTrue(Gate1File.objects.filter(pk=second).exists())
        self.food.review_status='manager';self.food.save()
        html=self.client.get(self.url).content.decode()
        for filename in ('a.pdf','b.pdf','updated-b.pdf'): self.assertIn(filename,html)
        download=self.client.get('/gate1/files/%s/'%replacement)
        self.assertEqual(b''.join(download.streaming_content),b'Updated specification B')
        self.assertEqual(self.client.post(self.url,{'action':'gate1_save',PREFIX+'-TOTAL_FORMS':'0'}).status_code,403)

    def test_invalid_or_foreign_files_rejected_and_legacy_files_still_visible(self):
        old=save_slot_file(self.food,self.user,'G1-F4',SimpleUploadedFile('legacy.pdf',b'Legacy specification'))
        other=Food.objects.create(name='Other',owner=self.user,stage='gate1')
        foreign=save_slot_file(other,self.user,'G1-F4',SimpleUploadedFile('other.pdf',b'Other specification'))
        wrong_slot=save_slot_file(self.food,self.user,'G1-F1',SimpleUploadedFile('tasting.pdf',b'Tasting'))
        for attachment in (foreign.pk,wrong_slot.pk,'invalid'):
            response=self.client.post(self.url,{'action':'gate1_save',PREFIX+'-TOTAL_FORMS':'1',
                PREFIX+'-0-material':'Material',PREFIX+'-0-attachment':attachment})
            self.assertEqual(response.status_code,200)
            self.assertIn(PREFIX,response.context['gate1form'].errors)
        html=self.client.get(self.url).content.decode()
        group=html.split('<fieldset class="gate0-identity gate1-materials"',1)[1].split('</fieldset>',1)[0]
        self.assertIn('legacy.pdf',group)
        self.assertIn(old.download_url,group)
