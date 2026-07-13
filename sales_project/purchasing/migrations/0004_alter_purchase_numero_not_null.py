from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchasing', '0003_backfill_numero'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchase',
            name='numero',
            field=models.CharField(
                blank=True, max_length=20, null=False, unique=True,
            ),
        ),
    ]
