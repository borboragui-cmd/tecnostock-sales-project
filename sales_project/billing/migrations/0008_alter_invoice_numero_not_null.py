from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_backfill_numero'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='numero',
            field=models.CharField(
                blank=True, max_length=20, null=False, unique=True,
                verbose_name='Número de Factura',
            ),
        ),
    ]
