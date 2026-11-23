import tempfile
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase

from .gate0 import Gate0Form,initial_brief,save_brief
from .gate0_rows import EvidenceRow,RowsField
from .models import Food,Gate0Evidence,Gate0File


class Gate0EvidenceTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user=User.objects.create_superuser('evidence-editor')
        self.food=Food.objects.create(name='Evidence example',owner=self.user)
        self.client.force_login(self.user)

    def test_evidence_matches_competitor_row_layout_with_new_heading(self):
        form=Gate0Form()
        self.assertIsInstance(form.fields['evidence'],RowsField)
        self.assertIs(form.fields['evidence'].row_form,EvidenceRow)
        self.assertEqual(form.fields['evidence'].gate_number,'2.4')
        self.assertEqual(form.fields['evidence'].label,'Нотолгоо')
        self.assertEqual(EvidenceRow().fields['file'].label,'Хэрэглэгчийн нотолгоо')
        self.assertEqual(form.fields['evidence'].widget.template_name,form.fields['competitor_benchmark'].widget.template_name)
        html=render_to_string('gate0_fields.html',{'form':form})
        self.assertIn('data-prefix="evidence"',html)
        self.assertIn('name="evidence-0-evidence_level"',html)
        self.assertIn('name="evidence-__prefix__-evidence_level"',html)
        self.assertNotIn('>0.6<',html)
        self.assertNotIn('name="evidence_level"',html)

    def test_multiple_rows_save_reload_and_delete_without_affecting_competitors(self):
        url='/food/%s/'%self.food.pk
        payload={
            'action':'gate0_save','evidence-TOTAL_FORMS':'2',
            'evidence-0-customer_need_evidence':'POS growth',
            'evidence-0-evidence_level':'A','evidence-0-evidence_reference':'POS report',
            'evidence-1-customer_need_evidence':'Customer requests',
            'evidence-1-evidence_level':'B','evidence-1-evidence_reference':'Survey',
            'competitor_benchmark-TOTAL_FORMS':'1','competitor_benchmark-0-product':'Other product',
        }
        self.assertEqual(self.client.post(url,payload).status_code,302)
        saved=initial_brief(self.food)
        self.assertEqual([row['evidence_level'] for row in saved['evidence']],['A','B'])
        self.assertEqual(saved['competitor_benchmark'][0]['product'],'Other product')
        self.assertContains(self.client.get(url),'POS growth')
        self.assertContains(self.client.get(url),'Customer requests')
        self.assertEqual(Gate0Evidence.objects.filter(gate_id=self.food.pk).count(),2)
        payload['evidence-0-DELETE']='1'
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual([row['evidence_level'] for row in initial_brief(self.food)['evidence']],['B'])
        payload['evidence-1-DELETE']='1'
        self.assertEqual(self.client.post(url,payload).status_code,302)
        self.assertEqual(initial_brief(self.food)['evidence'],[])

    def test_legacy_evidence_is_visible_and_survives_conversion(self):
        legacy={'customer_need_evidence':'Saved notes','evidence_level':'A','evidence_reference':'Saved source'}
        save_brief(self.food,legacy)
        saved=initial_brief(self.food)
        self.assertEqual(saved['evidence'],[legacy])
        form=Gate0Form(initial=dict(legacy))
        self.assertEqual(form['evidence'].value(),[legacy])
        form=Gate0Form(legacy)
        self.assertTrue(form.is_valid(),form.errors)
        save_brief(self.food,form.cleaned_data)
        converted=initial_brief(self.food)['evidence'][0]
        self.assertEqual({key:converted[key] for key in legacy},legacy)

    def test_files_upload_to_each_row_and_survive_edit_and_row_removal(self):
        url='/food/%s/'%self.food.pk
        payload={'action':'gate0_save','evidence-TOTAL_FORMS':'2',
                 'evidence-0-file':SimpleUploadedFile('pos.pdf',b'POS evidence'),
                 'evidence-1-file':SimpleUploadedFile('survey.csv',b'Survey evidence')}
        self.assertEqual(self.client.post(url,payload).status_code,302)
        rows=initial_brief(self.food)['evidence']
        self.assertEqual(len(rows),2)
        ids=[row['attachment'] for row in rows]
        self.assertEqual(len(set(ids)),2)
        self.assertEqual(Gate0File.objects.filter(development=self.food).count(),2)
        response=self.client.get(url)
        self.assertContains(response,'name="evidence-0-file"')
        self.assertContains(response,'pos.pdf')
        self.assertContains(response,'survey.csv')
        download=self.client.get('/gate0/files/%s/'%ids[0])
        self.assertEqual(download.status_code,200)
        self.assertEqual(b''.join(download.streaming_content),b'POS evidence')
        edited={'action':'gate0_save','evidence-TOTAL_FORMS':'2',
                'evidence-0-attachment':ids[0],'evidence-1-attachment':ids[1],
                'evidence-0-customer_need_evidence':'Updated notes'}
        self.assertEqual(self.client.post(url,edited).status_code,302)
        self.assertEqual([row['attachment'] for row in initial_brief(self.food)['evidence']],ids)
        edited['evidence-0-DELETE']='1'
        self.assertEqual(self.client.post(url,edited).status_code,302)
        self.assertEqual(initial_brief(self.food)['evidence'][0]['attachment'],ids[1])
        self.assertTrue(Gate0File.objects.filter(pk=ids[0]).exists())

    def test_creation_accepts_evidence_upload_and_replacement_keeps_history(self):
        response=self.client.post('/food/new/',{'evidence-TOTAL_FORMS':'1',
            'evidence-0-file':SimpleUploadedFile('initial.pdf',b'original')})
        self.assertEqual(response.status_code,302)
        food=Food.objects.exclude(pk=self.food.pk).get()
        original=initial_brief(food)['evidence'][0]['attachment']
        response=self.client.post(response.url,{'action':'gate0_save','evidence-TOTAL_FORMS':'1',
            'evidence-0-attachment':original,'evidence-0-file':SimpleUploadedFile('replacement.pdf',b'replacement')})
        self.assertEqual(response.status_code,302)
        replacement=initial_brief(food)['evidence'][0]['attachment']
        self.assertNotEqual(original,replacement)
        self.assertTrue(Gate0File.objects.filter(pk=original).exists())

    def test_foreign_attachment_and_locked_upload_are_rejected(self):
        other=Food.objects.create(name='Other',owner=self.user)
        from .gate0 import save_slot_file
        foreign=save_slot_file(other,self.user,'G0-F1',SimpleUploadedFile('other.pdf',b'other'))
        form=Gate0Form({'evidence':[{'attachment':foreign.pk}]},food=self.food)
        self.assertFalse(form.is_valid())
        self.assertIn('evidence',form.errors)
        self.food.review_status='manager';self.food.save()
        response=self.client.post('/food/%s/'%self.food.pk,{
            'action':'gate0_save','evidence-TOTAL_FORMS':'1',
            'evidence-0-file':SimpleUploadedFile('blocked.pdf',b'blocked')})
        self.assertEqual(response.status_code,403)
        self.assertFalse(Gate0File.objects.filter(development=self.food).exists())

    def test_invalid_attachment_id_renders_validation_error(self):
        response=self.client.post('/food/%s/'%self.food.pk,{
            'action':'gate0_save','evidence-TOTAL_FORMS':'1','evidence-0-attachment':'invalid'})
        self.assertEqual(response.status_code,200)
        self.assertIn('evidence',response.context['gate0form'].errors)

    def test_partial_rows_are_optional_and_types_are_validated(self):
        for rows in [[],[{}],[{'customer_need_evidence':'Notes only'}]]:
            form=Gate0Form({'evidence':rows})
            self.assertTrue(form.is_valid(),form.errors)
        form=Gate0Form({'evidence':[{'evidence_level':'invalid'}]})
        self.assertFalse(form.is_valid())
        self.assertIn('evidence',form.errors)

    def test_shared_evidence_types_and_readonly_rows(self):
        response=self.client.post('/api/dropdown-options/',{
            'stage':'gate0','field':'evidence.evidence_level','label':'Research',
        },content_type='application/json')
        self.assertEqual(response.status_code,201)
        form=Gate0Form({'evidence':[{'evidence_level':'Research'}]})
        self.assertTrue(form.is_valid(),form.errors)
        form.fields['evidence'].disabled=True
        html=str(form['evidence'])
        self.assertNotIn('data-add-row',html)
        self.assertNotIn('-DELETE',html)
        self.assertIn('disabled',html)
