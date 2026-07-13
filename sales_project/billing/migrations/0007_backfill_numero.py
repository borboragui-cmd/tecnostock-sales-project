from django.db import migrations


def backfill_numero(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    for invoice in Invoice.objects.filter(numero__isnull=True):
        invoice.numero = f'FAC-{invoice.pk:06d}'
        invoice.tipo_pago = 'CONTADO'
        invoice.saldo = 0
        invoice.estado = 'PAGADA'
        invoice.save(update_fields=['numero', 'tipo_pago', 'saldo', 'estado'])


def reverse_backfill(apps, schema_editor):
    pass  # no reversible, no hace falta


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0006_invoice_estado_invoice_numero_invoice_saldo_and_more'),
    ]
    operations = [
        migrations.RunPython(backfill_numero, reverse_backfill),
    ]
