from django.db import migrations

def seed(apps, schema_editor):
    apps.get_model('development', 'TargetCostingSettings').objects.get_or_create(pk=1, defaults={'vat_percent':'10.00'})

class Migration(migrations.Migration):
    dependencies = [('development', '0025_targetcostingsettings')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
