from django.db import migrations


def backfill_numero(apps, schema_editor):
    Purchase = apps.get_model('purchasing', 'Purchase')
    for purchase in Purchase.objects.filter(numero__isnull=True):
        purchase.numero = f'ORD-{purchase.pk:06d}'
        purchase.tipo_pago = 'CONTADO'
        purchase.saldo = 0
        purchase.estado = 'PAGADA'
        purchase.save(update_fields=['numero', 'tipo_pago', 'saldo', 'estado'])


def reverse_backfill(apps, schema_editor):
    pass  # no reversible, no hace falta


class Migration(migrations.Migration):
    dependencies = [
        ('purchasing', '0002_purchase_numero_tipo_pago_saldo_estado'),
    ]
    operations = [
        migrations.RunPython(backfill_numero, reverse_backfill),
    ]
