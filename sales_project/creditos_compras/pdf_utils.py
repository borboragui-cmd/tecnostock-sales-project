from io import BytesIO
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def _comandos_tabla_estandar():
    return [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#212529')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]


def _estilo_tabla_estandar():
    return TableStyle(_comandos_tabla_estandar())


def generar_pdf_plan_pagos(compra):
    """Cronograma completo de cuotas de una compra a crédito."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elementos = [
        Paragraph(f'Plan de Pagos - Compra {compra.numero}', styles['Title']),
        Spacer(1, 0.4*cm),
        Paragraph(f'Proveedor: {compra.supplier.name}', styles['Normal']),
        Paragraph(f'N° Factura Proveedor: {compra.document_number}', styles['Normal']),
        Paragraph(f'Fecha de compra: {compra.purchase_date.strftime("%d/%m/%Y")}', styles['Normal']),
        Paragraph(f'Total: ${compra.total}', styles['Normal']),
        Paragraph(f'Saldo pendiente: ${compra.saldo}', styles['Normal']),
        Paragraph(f'Estado: {compra.estado}', styles['Normal']),
        Spacer(1, 0.6*cm),
    ]

    data = [['N°', 'Vencimiento', 'Valor', 'Saldo', 'Estado']]
    for cuota in compra.cuotas.order_by('numero'):
        estado_mostrado = 'VENCIDA' if cuota.esta_vencida else cuota.estado
        data.append([str(cuota.numero), cuota.fecha_vencimiento.strftime('%d/%m/%Y'),
                     f'${cuota.valor}', f'${cuota.saldo}', estado_mostrado])

    tabla = Table(data, colWidths=[1.5*cm, 3.5*cm, 3*cm, 3*cm, 3*cm])
    tabla.setStyle(_estilo_tabla_estandar())
    elementos.append(tabla)

    doc.build(elementos)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="plan_pagos_{compra.numero}.pdf"'
    return response


def generar_pdf_comprobante_lote(pagos):
    """Un solo PDF consolidado con todos los pagos registrados en un envío
    (cuando el usuario paga varias cuotas a la vez)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    sello_style = ParagraphStyle(
        'Sello', parent=styles['Heading1'], alignment=1,
        textColor=colors.HexColor('#16A34A'), spaceAfter=2,
    )
    marca_tiempo_style = ParagraphStyle(
        'MarcaTiempo', parent=styles['Normal'], alignment=1,
        textColor=colors.grey, fontSize=9, spaceAfter=14,
    )
    detalle_style = ParagraphStyle(
        'Detalle', parent=styles['Normal'], fontSize=8,
        textColor=colors.HexColor('#495057'), leftIndent=4,
    )

    ahora = timezone.localtime()
    elementos = [
        Paragraph('PAGO APROBADO', sello_style),
        Paragraph(f'Generado el {ahora.strftime("%d/%m/%Y %H:%M:%S")}', marca_tiempo_style),
        Paragraph('Comprobante de Pago', styles['Title']),
        Spacer(1, 0.4*cm),
    ]

    total_pagado = sum(p.valor for p in pagos)
    data = [['Compra', 'Proveedor', 'Cuota N°', 'Fecha', 'Valor']]
    comandos = _comandos_tabla_estandar()

    for pago in pagos:
        cuota = pago.cuota
        data.append([
            cuota.compra.numero, cuota.compra.supplier.name,
            str(cuota.numero), pago.fecha.strftime('%d/%m/%Y'), f'${pago.valor}',
        ])

        if pago.interes_mora or pago.descuento_pronto_pago:
            capital = pago.valor - pago.interes_mora + pago.descuento_pronto_pago
            if pago.interes_mora:
                detalle_texto = f'Capital: ${capital} — Interés de mora: ${pago.interes_mora}'
            else:
                detalle_texto = f'Capital: ${capital} — Descuento pronto pago: ${pago.descuento_pronto_pago}'
            fila_idx = len(data)
            data.append([Paragraph(detalle_texto, detalle_style), '', '', '', ''])
            comandos.append(('SPAN', (0, fila_idx), (-1, fila_idx)))
            comandos.append(('ALIGN', (0, fila_idx), (-1, fila_idx), 'LEFT'))
            comandos.append(('BACKGROUND', (0, fila_idx), (-1, fila_idx), colors.HexColor('#FFF7E6')))

    tabla = Table(data, colWidths=[3*cm, 4*cm, 2*cm, 2.5*cm, 2.5*cm])
    tabla.setStyle(TableStyle(comandos))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.5*cm))
    elementos.append(Paragraph(f'<b>Total pagado: ${total_pagado}</b>', styles['Normal']))

    doc.build(elementos)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="comprobante_pago_compras.pdf"'
    return response
