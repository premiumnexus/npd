from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('development', '0039_gate2_quality_standard_file'),
    ]

    operations = [
        # Django 4.2 does not rewrite fields inside named constraints during RenameField.
        migrations.RemoveConstraint(
            model_name='launchcheckpoint',
            name='unique_launch_checkpoint_day',
        ),
        migrations.RenameField(
            model_name='launchcheckpoint',
            old_name='food',
            new_name='development',
        ),
        migrations.AddConstraint(
            model_name='launchcheckpoint',
            constraint=models.UniqueConstraint(
                fields=('development', 'day'),
                name='unique_launch_checkpoint_day',
            ),
        ),
    ]
