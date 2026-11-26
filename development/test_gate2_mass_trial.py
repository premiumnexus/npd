from django.contrib.auth.models import User
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
        self.assertEqual(form.fields['unit_weight_variation'].gate_number, '2.10')

    def test_detail_renders_section_with_note_before_other_fields(self):
        html = self.client.get('/food/%s/' % self.food.pk).content.decode()
        section = html.index('<legend>Масс туршилт</legend>')
        self.assertIn('Үйлдвэрт тогтвортой хийж чадах уу?', html)
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


COMPLETE = {
    'mass_trial_result': '25', 'trial_date': '2027-03-01', 'trial_yield_percent': '95',
    'trial_taste_score': '4', 'quality_tolerance_baseline': '150', 'quality_weight_min': '145',
    'quality_weight_max': '155', 'unit_weight_mean': '150.5',
    'final_technology_transfer_document': 'v1', 'technology_transfer_date': '2027-03-02',
}
