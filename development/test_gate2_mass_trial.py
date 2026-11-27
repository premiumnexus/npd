import tempfile
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .gate2_typed import Gate2Form
from .models import Food


MASS_TRIAL = [
    ('mass_trial_result', '1.1', 'Масс туршилтын багц (кг)'),
    ('trial_date', '1.2', 'Туршилтын огноо'),
    ('trial_yield_percent', '1.3', 'Туршилтын гарц (%)'),
    ('trial_taste_score', '1.4', 'Амтын үнэлгээ (1–5)'),
    ('quality_tolerance_baseline', '1.5', 'Жингийн зорилт (г)'),
    ('quality_weight_min', '1.6', 'Жингийн доод хязгаар (г)'),
    ('quality_weight_max', '1.7', 'Жингийн дээд хязгаар (г)'),
    ('unit_weight_mean', '1.8', 'Масс туршилтын нэгжийн дундаж жин (г)'),
    ('final_technology_transfer_document', '1.9', 'Технологи шилжүүлэх баримтын хувилбар'),
    ('technology_transfer_date', '1.10', 'Баримтын огноо'),
]


class Gate2MassTrialSectionTests(TestCase):
    def setUp(self):
        self.media=tempfile.TemporaryDirectory();self.addCleanup(self.media.cleanup)
        override=self.settings(MEDIA_ROOT=self.media.name)
        override.enable();self.addCleanup(override.disable)
        self.user = User.objects.create_superuser('gate2-mass-trial', password='x')
        self.food = Food.objects.create(name='Mass trial', stage='gate2', category='FF', owner=self.user)
        self.client.force_login(self.user)

    def test_fields_are_renumbered_in_order(self):
        form = Gate2Form(food=self.food)
        section = [name for name, field in form.fields.items() if field.gate_number.startswith('1.')]
        self.assertEqual(section, [name for name, _, _ in MASS_TRIAL])
        for name, number, label in MASS_TRIAL:
            self.assertEqual(form.fields[name].gate_number, number)
            self.assertEqual(form.fields[name].label, label)
            self.assertTrue(form.fields[name].help_text.startswith(number + ' · '))
        self.assertNotIn('unit_weight_variation',form.fields)

    def test_detail_renders_section_with_note_before_other_fields(self):
        html = self.client.get('/food/%s/' % self.food.pk).content.decode()
        section = html.index('<legend>Үйлдвэрлэл</legend>')
        self.assertIn('Үйлдвэрт бүрэн хэмжээгээр ижил гарч байна уу?', html)
        positions = [html.index('name="%s"' % name) for name, _, _ in MASS_TRIAL]
        self.assertTrue(section < positions[0])
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], html.index('name="lab_results_approved_shelf_life"'))
        for name, _, _ in MASS_TRIAL:
            self.assertEqual(html.count('name="%s"' % name), 1, name)

    def test_section_fields_show_required_star(self):
        html = self.client.get('/food/%s/' % self.food.pk).content.decode()
        for name, number, label in MASS_TRIAL:
            self.assertIn('<span class="field-number">%s</span> %s <span class="required-star"' % (number, label), html)
        self.assertNotIn('<span class="field-number">2.10</span> Нэгжийн жингийн хэлбэлзэл (± г) <span class="required-star"', html)

    def test_draft_save_allows_partial_section(self):
        self.assertTrue(Gate2Form({'mass_trial_result': '10'}, food=self.food).is_valid())
        form = Gate2Form({'mass_trial_result': '10'}, food=self.food, submission=True)
        self.assertFalse(form.is_valid())
        self.assertEqual(set(form.errors) & {name for name, _, _ in MASS_TRIAL}, {name for name, _, _ in MASS_TRIAL[1:]})

    def test_submission_requires_section_then_advances_to_qa(self):
        from .gate2 import save_brief
        url = '/food/%s/' % self.food.pk
        self.client.post(url, {'action': 'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status, 'draft')
        save_brief(self.food, COMPLETE)
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .gate2 import save_slot_file
        save_slot_file(self.food,self.user,'G2-F2',SimpleUploadedFile('quote.pdf',b'quote'))
        save_slot_file(self.food,self.user,'G2-F5',SimpleUploadedFile('signed.pdf',b'signed transfer'))
        for slot in ('G2-F3','G2-F6','G2-F7','G2-F8'): save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'lab and safety'))
        self.client.post(url, {'action': 'submit'})
        self.food.refresh_from_db()
        self.assertEqual(self.food.review_status, 'qa')

    def test_approval_rechecks_section(self):
        from .models import Gate2
        self.food.review_status = 'manager'
        self.food.save()
        Gate2.objects.update_or_create(development_id=self.food.pk, defaults={'mass_trial_result': 10})
        self.client.post('/food/%s/' % self.food.pk, {'action': 'approve'})
        self.food.refresh_from_db()
        self.assertEqual((self.food.stage, self.food.review_status), ('gate2', 'manager'))

    def test_production_file_slots_are_numbered_once_and_not_at_the_bottom(self):
        html=self.client.get('/food/%s/'%self.food.pk).content.decode()
        group=html.split('<fieldset class="gate0-identity gate2-mass-trial"',1)[1].split('</fieldset>',1)[0]
        bottom=html.split('<section class="gate0-file-slots"',1)[1]
        positions=[]
        for key,number in [('G2-F5','1.11'),('G2-F1','1.12'),('G2-F13','1.13')]:
            positions.append(group.index('class="field-number">%s</span>'%number))
            self.assertEqual(html.count('id="file-%s"'%key),1)
            self.assertIn('id="file-%s"'%key,group)
            self.assertNotIn('id="file-%s"'%key,bottom)
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(group.count('class="required-star"'),11)
        self.assertNotIn('name="unit_weight_variation"',html)

    def test_signed_transfer_file_required_before_submission_and_approval(self):
        from .gate2 import save_brief,save_slot_file
        url='/food/%s/'%self.food.pk
        save_brief(self.food,COMPLETE)
        save_slot_file(self.food,self.user,'G2-F2',SimpleUploadedFile('quote.pdf',b'quote'))
        for slot in ('G2-F3','G2-F6','G2-F7','G2-F8'): save_slot_file(self.food,self.user,slot,SimpleUploadedFile(slot+'.pdf',b'lab and safety'))
        form=Gate2Form(COMPLETE,food=self.food,submission=True)
        self.assertFalse(form.is_valid());self.assertIn('1.11',str(form.non_field_errors()))
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'draft')
        self.food.review_status='manager';self.food.save()
        self.client.post(url,{'action':'approve'})
        self.food.refresh_from_db();self.assertEqual((self.food.stage,self.food.review_status),('gate2','manager'))
        self.food.review_status='draft';self.food.save()
        upload=self.client.post(url,{'action':'slot_upload','slot':'G2-F5','slot_file':SimpleUploadedFile('signed.pdf',b'signed transfer')})
        self.assertEqual(upload.status_code,302)
        form=Gate2Form(COMPLETE,food=self.food,submission=True)
        self.assertTrue(form.is_valid(),form.errors)
        self.client.post(url,{'action':'submit'})
        self.food.refresh_from_db();self.assertEqual(self.food.review_status,'qa')


COMPLETE = {
    'day45_units_store_day':'10','day45_writeoff_percent':'5',
    'marketing_has_promotion':'no',
    'launch_date':'2027-05-15','allocation':'100','first_order_units':'1000',
    'barcode_system_registration':'00123456789','sku_code_requested':'yes',
    'pos_name_price_checked':'yes','supply_readiness':'yes','cold_chain_temperature':'chilled',
    'label_allergens':'Milk','label_checked':'yes',
    'nutrition_info':[{'energy_kcal':'200','protein_g':'5','fat_g':'10','carbohydrates_g':'20','salt_g':'0.5'}],
    'lab_results_approved_shelf_life':'pass','approved_shelf_life_hours':'48',
    'vendor_invoice_price':'1000',
    'mass_trial_result': '25', 'trial_date': '2027-03-01', 'trial_yield_percent': '95',
    'trial_taste_score': '4', 'quality_tolerance_baseline': '150', 'quality_weight_min': '145',
    'quality_weight_max': '155', 'unit_weight_mean': '150.5',
    'final_technology_transfer_document': 'v1', 'technology_transfer_date': '2027-03-02',
}
