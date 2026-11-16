import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.utils import timezone

from .gate0_typed import Gate0Form
from .gate1_typed import Gate1Form, MaterialRow
from .models import Food, SharedDropdownOption


class SharedDropdownTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('options-admin', password='test')
        self.client.force_login(self.user)
        self.food = Food.objects.create(name='Example', owner=self.user, stage='gate1')

    def add(self, **values):
        payload = {'stage': 'gate0', 'field': 'daypart', 'label': 'New occasion'}
        payload.update(values)
        return self.client.post('/api/dropdown-options/', json.dumps(payload), content_type='application/json')

    def test_saved_option_available_to_another_user_and_valid_on_submit(self):
        response = self.add()
        self.assertEqual(response.status_code, 201)
        value = response.json()['value']
        self.client.force_login(User.objects.create_superuser('other-admin', password='test'))
        page = self.client.get('/food/new/')
        self.assertContains(page, 'New occasion')
        form = Gate0Form({'daypart': value})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['daypart'], [value])
        self.assertEqual(self.add(label='  new   OCCASION ').status_code, 200)
        self.assertEqual(SharedDropdownOption.objects.count(), 1)

    def test_subcategories_are_scoped_and_survive_category_changes(self):
        self.assertEqual(self.add(field='subcategory', scope='FF', label='New subcategory').status_code, 201)
        ff = Gate0Form(initial={'category': 'FF'})
        isf = Gate0Form(initial={'category': 'ISF'})
        self.assertIn(('New subcategory', 'New subcategory'), ff.fields['subcategory'].choices)
        self.assertNotIn(('New subcategory', 'New subcategory'), isf.fields['subcategory'].choices)
        self.assertIn('New subcategory', isf.fields['subcategory'].widget.attrs['data-options'])
        self.assertEqual(self.add(field='subcategory', scope='unknown').status_code, 400)

    def test_every_gate_and_repeat_row_loads_shared_choices(self):
        from .gate2_typed import Gate2Form
        from .gate3_typed import Gate3Form
        for stage, form_class, field in [('gate1', Gate1Form, 'capacity_constraint'),
                                          ('gate2', Gate2Form, 'label_checked'),
                                          ('gate3', Gate3Form, 'root_cause')]:
            self.food.stage = stage
            self.food.launched_at = timezone.now() - timedelta(days=46)
            self.food.save()
            response = self.add(stage=stage, field=field, food=self.food.pk, label='Shared label')
            self.assertEqual(response.status_code, 201)
            form = form_class({field: 'Shared label'}, food=self.food)
            self.assertTrue(form.is_valid(), form.errors)
        self.food.stage = 'gate1'
        self.food.save()
        response = self.add(stage='gate1', field='raw_material_spec_price_moq_second_source.spec_written',
                            food=self.food.pk, label='Pending')
        self.assertEqual(response.status_code, 201)
        self.assertIn(('Pending', 'Pending'), MaterialRow().fields['spec_written'].choices)
        form = Gate1Form({'raw_material_spec_price_moq_second_source-TOTAL_FORMS': '1',
                          'raw_material_spec_price_moq_second_source-0-spec_written': 'Pending'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_permissions_and_locked_fields(self):
        self.assertEqual(self.add(stage='gate2', field='label_checked', food=self.food.pk).status_code, 403)
        self.food.review_status = 'manager'
        self.food.save()
        self.assertEqual(self.add(stage='gate1', field='capacity_constraint', food=self.food.pk).status_code, 403)
        self.client.force_login(User.objects.create_user('viewer', password='test'))
        self.assertEqual(self.add().status_code, 403)
        self.assertEqual(self.add(stage='gate1', field='capacity_constraint', food=self.food.pk).status_code, 403)
        self.assertEqual(SharedDropdownOption.objects.count(), 0)

    def test_invalid_requests_and_existing_choices(self):
        for values in [{'label': ''}, {'label': '__add_option__'}, {'field': 'product_name'},
                       {'field': 'missing'}, {'label': 'x' * 201}, {'scope': 'FF'}, {'stage': 'bad'}]:
            self.assertEqual(self.add(**values).status_code, 400)
        self.assertEqual(self.add(label=' morning ').status_code, 200)
        existing = self.add(label='\u04e8\u0433\u043b\u04e9\u04e9')
        self.assertEqual(existing.status_code, 200)
        self.assertEqual(existing.json()['value'], 'morning')
        self.assertEqual(self.client.post('/api/dropdown-options/', '[1]', content_type='application/json').status_code, 400)

    def test_recipe_ingredient_is_saved_with_price_and_supplier(self):
        from .forms import Gate1LineForm
        from .models import Ingredient, Supplier
        response = self.add(stage='gate1', field='recipe_ingredient', food=self.food.pk,
                            label='New ingredient', supplier='New supplier', price='4500.00')
        self.assertEqual(response.status_code, 201)
        ingredient = Ingredient.objects.get(pk=response.json()['value'])
        self.assertEqual(ingredient.supplier.name, 'New supplier')
        self.assertEqual(ingredient.unit, 'kg')
        form = Gate1LineForm({'ingredient': ingredient.pk, 'net_grams': '100'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['unit_price'], ingredient.price)
        self.assertEqual(Supplier.objects.filter(name='New supplier').count(), 1)
        repeated = self.add(stage='gate1', field='recipe_ingredient', food=self.food.pk,
                            label='New ingredient', supplier='New supplier', price='6000.00')
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()['price'], '4500.00')
        self.assertEqual(Ingredient.objects.filter(name='New ingredient').count(), 1)
        invalid = self.add(stage='gate1', field='recipe_ingredient', food=self.food.pk,
                           label='Invalid ingredient', supplier='Invalid supplier', price='-1')
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(Supplier.objects.filter(name='Invalid supplier').exists())

    def test_gate2_recipe_ingredient_can_be_created_and_used_in_recipe(self):
        from .models import Ingredient
        self.food.stage='gate2'; self.food.save()
        response=self.add(stage='gate2',field='recipe_ingredient',food=self.food.pk,
                          label='Gate 2 ingredient',supplier='Gate 2 supplier',price='4500')
        self.assertEqual(response.status_code,201)
        ingredient=Ingredient.objects.get(pk=response.json()['value'])
        result=self.client.post('/food/%s/' % self.food.pk,{'action':'gate2_line_add','ingredient':ingredient.pk,'net_grams':'100'})
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.food.lines.get().unit_price,ingredient.price)
        self.food.review_status='qa'; self.food.save()
        self.assertEqual(self.add(stage='gate2',field='recipe_ingredient',food=self.food.pk,
                                 label='Locked ingredient',supplier='Gate 2 supplier',price='4500').status_code,403)
        self.assertFalse(Ingredient.objects.filter(name='Locked ingredient').exists())

    def test_added_option_remains_selected_after_food_is_saved(self):
        response = self.add(label='New occasion')
        result = self.client.post('/food/new/', {'product_name': 'Saved food', 'daypart': response.json()['value']})
        self.assertEqual(result.status_code, 302)
        self.assertContains(self.client.get(result.url), '<option value="New occasion" selected>New occasion</option>', html=True)

    def test_add_action_is_render_only_and_placeholder_stays_unselectable(self):
        from html.parser import HTMLParser
        class Options(HTMLParser):
            def __init__(self):
                super().__init__()
                self.options = []
            def handle_starttag(self, tag, attrs):
                if tag == 'option': self.options.append(dict(attrs))
        form = Gate0Form()
        html = render_to_string('gate0_fields.html', {'form': form})
        parsed = Options()
        parsed.feed(html)
        self.assertTrue(any(option['value'] == '__add_option__' for option in parsed.options))
        self.assertTrue(any('disabled' in option and 'hidden' in option for option in parsed.options))
        self.assertNotIn('__add_option__', dict(form.fields['subcategory'].choices))
        invalid = Gate0Form({'daypart': '__add_option__'})
        self.assertFalse(invalid.is_valid())
        form.fields['subcategory'].disabled = True
        self.assertNotIn('__add_option__', str(form['subcategory']))

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/api/dropdown-options/', '{}', content_type='application/json').status_code, 403)

    def test_dayparts_allow_multiple_values_and_preserve_older_briefs(self):
        from .gate0 import save_brief, initial_brief
        form = Gate0Form({'daypart': ['morning', 'lunch']})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['daypart'], ['morning', 'lunch'])
        save_brief(self.food, form.cleaned_data)
        saved = initial_brief(self.food)
        self.assertEqual(saved['daypart'], ['morning', 'lunch'])
        restored = Gate0Form(initial=saved)
        self.assertEqual(restored['daypart'].value(), ['morning', 'lunch'])
        old = Gate0Form(initial={'daypart': 'evening'})
        self.assertFalse(old.legacy_values)
        self.assertIn('value="evening" selected', str(old['daypart']))
        old_post = Gate0Form({'daypart': 'evening'})
        self.assertTrue(old_post.is_valid(), old_post.errors)
        self.assertEqual(old_post.cleaned_data['daypart'], ['evening'])
        empty = Gate0Form({})
        self.assertTrue(empty.is_valid(), empty.errors)
        self.assertEqual(empty.cleaned_data['daypart'], [])

    def test_multiple_dayparts_and_shared_option_saved_from_browser_post(self):
        response = self.add(label='New occasion')
        self.assertEqual(response.status_code, 201)
        result = self.client.post('/food/new/', {'product_name': 'Multi dayparts',
                                               'daypart': ['morning', response.json()['value']]})
        self.assertEqual(result.status_code, 302)
        from .gate0 import initial_brief
        food = Food.objects.get(name='Multi dayparts')
        self.assertEqual(initial_brief(food)['daypart'], ['morning', 'New occasion'])
        self.assertContains(self.client.get(result.url), 'data-multiselect')
