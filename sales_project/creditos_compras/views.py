import secrets
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView

from purchasing.models import Purchase
from shared.mixins import ExportMixin
from .models import CuotaCompra, PagoCuotaCompra
from .forms import PagoCuotaCompraForm
from . import services
from . import pdf_utils


def _parsear_formset_a_pagos_data(formset):
    """Recorre un formset ya validado (PagoCuotaCompraForm) y arma la
    lista de pagos a procesar. Compartido entre el submit directo
    (registrar_pagos) y el submit vía PayPal simulado (pagar_con_paypal)
    para no duplicar este parsing en dos lados.
    Devuelve (pagos_data, error): si error no es None, pagos_data es None.
    """
    pagos_data = []
    hoy = timezone.localdate()
    print('[DEBUG-PAGOS] _parsear_formset_a_pagos_data (compras): recorriendo', len(formset.forms), 'filas')
    for i, form in enumerate(formset):
        pagar_raw = form.data.get(form.add_prefix('pagar'))
        pagar_clean = form.cleaned_data.get('pagar')
        print(f'[DEBUG-PAGOS] fila {i}: cuota_id={form.cleaned_data.get("cuota_id")} '
              f'pagar_raw_en_POST={pagar_raw!r} pagar_cleaned={pagar_clean!r} '
              f'valor={form.cleaned_data.get("valor")!r} fecha={form.cleaned_data.get("fecha")!r}')
        if form.cleaned_data.get('pagar'):
            print(f'[DEBUG-PAGOS]   -> fila {i} MARCADA para pagar')
            valor = form.cleaned_data.get('valor')
            if not valor:
                return None, 'Debes indicar un valor para cada cuota marcada.'
            fecha = form.cleaned_data.get('fecha')
            if fecha and fecha != hoy:
                # Defensa en profundidad, mismo criterio que
                # creditos_ventas/views.py — el input ya es readonly en el
                # template, esto cubre un POST manual saltándose la UI.
                return None, 'La fecha de pago debe ser la fecha actual.'
            pagos_data.append({
                'cuota_id': form.cleaned_data['cuota_id'],
                'valor': valor,
                'observacion': form.cleaned_data.get('observacion', ''),
            })
        else:
            print(f'[DEBUG-PAGOS]   -> fila {i} DESCARTADA (pagar no marcado)')
    print('[DEBUG-PAGOS] resultado final pagos_data:', pagos_data)
    return pagos_data, None


class CuotaCompraPendientesListView(LoginRequiredMixin, ExportMixin, ListView):
    """Consulta global de cuotas pendientes, con filtro opcional por compra.
    Hereda de ExportMixin para exponer exportación a PDF/Excel sin duplicar
    la lógica ya usada en CuotaVentaPendientesListView / ProductListView."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuotas_pendientes.html'
    context_object_name = 'cuotas'

    export_fields = [
        ('compra.numero', 'Compra'),
        ('compra.supplier', 'Proveedor'),
        ('numero', 'N° Cuota'),
        ('fecha_vencimiento', 'Vencimiento'),
        ('valor', 'Valor'),
        ('saldo', 'Saldo'),
        ('estado', 'Estado'),
    ]
    export_filename = 'cuotas_pendientes_compras'
    export_title = 'Cuotas Pendientes de Compras'

    def get_queryset(self):
        qs = CuotaCompra.objects.select_related('compra', 'compra__supplier').filter(estado='PENDIENTE')
        compra_id = self.request.GET.get('compra')
        if compra_id:
            qs = qs.filter(compra_id=compra_id)
        return qs

    def get(self, request, *args, **kwargs):
        export_format = request.GET.get('export')
        if export_format == 'pdf':
            return self.export_to_pdf()
        if export_format == 'excel':
            return self.export_to_excel()
        return super().get(request, *args, **kwargs)


class CuotaCompraListView(LoginRequiredMixin, ListView):
    """Listado completo de cuotas (pendientes y pagadas) para auditoría."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_list.html'
    context_object_name = 'items'
    paginate_by = 25

    def get_queryset(self):
        return CuotaCompra.objects.select_related('compra', 'compra__supplier').all()


@login_required
def registrar_pagos(request, compra_id):
    """Muestra las cuotas pendientes de UNA compra, permite marcar varias
    para pagarlas en un solo envío (todo o nada)."""
    compra = get_object_or_404(Purchase, pk=compra_id)
    cuotas_qs = compra.cuotas.filter(estado='PENDIENTE').order_by('numero')

    PagoFormSet = formset_factory(PagoCuotaCompraForm, extra=0)

    if request.method == 'POST':
        print('=' * 80)
        print('[DEBUG-PAGOS] registrar_pagos (compras) POST recibido para compra_id=', compra_id)
        print('[DEBUG-PAGOS] request.POST completo:', dict(request.POST))
        formset = PagoFormSet(request.POST)
        print('[DEBUG-PAGOS] formset.is_valid() =', formset.is_valid())
        if not formset.is_valid():
            print('[DEBUG-PAGOS] formset.errors completo:', formset.errors)
            print('[DEBUG-PAGOS] formset.non_form_errors():', formset.non_form_errors())
        if formset.is_valid():
            pagos_data, error = _parsear_formset_a_pagos_data(formset)
            print('[DEBUG-PAGOS] registrar_pagos: pagos_data=', pagos_data, 'error=', error)
            if error:
                messages.error(request, error)
                return render(request, 'creditos_compras/registrar_pagos.html', {
                    'compra': compra, 'filas': list(zip(formset, cuotas_qs)),
                })

            if not pagos_data:
                messages.warning(request, 'No seleccionaste ninguna cuota para pagar.')
            else:
                try:
                    resultados = services.registrar_pagos_multiples(pagos_data)
                    print('[DEBUG-PAGOS] registrar_pagos_multiples OK, pagos creados:',
                          [(p.cuota_id, p.valor) for p in resultados])
                    request.session['ultimo_lote_pagos_compras'] = [str(p.id) for p in resultados]
                    messages.success(request, f'{len(pagos_data)} pago(s) registrado(s) correctamente.')
                    return redirect('creditos_compras:comprobante_lote')
                except ValidationError as e:
                    print('[DEBUG-PAGOS] registrar_pagos_multiples FALLO:', str(e))
                    messages.error(request, str(e))
    else:
        initial = [{'cuota_id': c.id, 'valor': c.saldo, 'fecha': timezone.localdate()} for c in cuotas_qs]
        formset = PagoFormSet(initial=initial)

    return render(request, 'creditos_compras/registrar_pagos.html', {
        'compra': compra, 'filas': list(zip(formset, cuotas_qs)),
    })


@login_required
def pagar_con_paypal(request, compra_id):
    """Etapa 1 del checkout de PayPal simulado: toma las mismas filas
    marcadas en el formset de registrar_pagos, pero en vez de guardar el
    pago de inmediato, lo deja en sesión y redirige al login falso de
    PayPal. No toca la BD todavía."""
    compra = get_object_or_404(Purchase, pk=compra_id)
    cuotas_qs = compra.cuotas.filter(estado='PENDIENTE').order_by('numero')
    PagoFormSet = formset_factory(PagoCuotaCompraForm, extra=0)

    if request.method != 'POST':
        return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)

    print('=' * 80)
    print('[DEBUG-PAGOS] pagar_con_paypal (compras) POST recibido para compra_id=', compra_id)
    print('[DEBUG-PAGOS] request.POST completo:', dict(request.POST))
    formset = PagoFormSet(request.POST)
    print('[DEBUG-PAGOS] pagar_con_paypal: formset.is_valid() =', formset.is_valid())
    if not formset.is_valid():
        print('[DEBUG-PAGOS] pagar_con_paypal: formset.errors completo:', formset.errors)
        print('[DEBUG-PAGOS] pagar_con_paypal: formset.non_form_errors():', formset.non_form_errors())
        messages.error(request, 'Revisa los datos del formulario antes de pagar con PayPal.')
        return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)

    pagos_data, error = _parsear_formset_a_pagos_data(formset)
    print('[DEBUG-PAGOS] pagar_con_paypal: pagos_data=', pagos_data, 'error=', error)
    if error:
        messages.error(request, error)
        return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)
    if not pagos_data:
        messages.warning(request, 'No seleccionaste ninguna cuota para pagar.')
        return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)

    request.session['paypal_pago_pendiente_compras'] = {
        'compra_id': compra.id,
        'pagos_data': [
            {'cuota_id': p['cuota_id'], 'valor': str(p['valor']), 'observacion': p['observacion']}
            for p in pagos_data
        ],
    }
    return redirect('creditos_compras:paypal_login', compra_id=compra.id)


@login_required
def paypal_login(request, compra_id):
    """Etapa 2: pantalla de login falso de PayPal. Ningún campo valida
    nada real — cualquier envío avanza a la confirmación."""
    compra = get_object_or_404(Purchase, pk=compra_id)
    pendiente = request.session.get('paypal_pago_pendiente_compras')
    if not pendiente or pendiente.get('compra_id') != compra.id:
        messages.error(request, 'No hay ningún pago pendiente de confirmar vía PayPal.')
        return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)

    if request.method == 'POST':
        return redirect('creditos_compras:paypal_confirmar', compra_id=compra.id)

    return render(request, 'creditos_compras/paypal_login.html', {'compra': compra})


@login_required
def paypal_confirmar(request, compra_id):
    """Etapa 3: pantalla de confirmación de pago. Al confirmar, ejecuta el
    pago real vía services.registrar_pagos_multiples (misma lógica de
    mora/descuento/liquidación de siempre) y le agrega metodo_pago='PAYPAL'
    + un ID de transacción falso a cada PagoCuotaCompra creado."""
    compra = get_object_or_404(Purchase, pk=compra_id)
    pendiente = request.session.get('paypal_pago_pendiente_compras')
    if not pendiente or pendiente.get('compra_id') != compra.id:
        messages.error(request, 'No hay ningún pago pendiente de confirmar vía PayPal.')
        return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)

    cuotas_por_id = {c.id: c for c in compra.cuotas.all()}
    filas = []
    total = Decimal('0.00')
    for p in pendiente['pagos_data']:
        valor = Decimal(p['valor'])
        total += valor
        filas.append({'cuota': cuotas_por_id.get(p['cuota_id']), 'valor': valor})

    if request.method == 'POST':
        pagos_data = [
            {
                'cuota_id': p['cuota_id'],
                'valor': Decimal(p['valor']),
                'observacion': p['observacion'],
            }
            for p in pendiente['pagos_data']
        ]
        try:
            resultados = services.registrar_pagos_multiples(pagos_data)
        except ValidationError as e:
            messages.error(request, str(e))
            del request.session['paypal_pago_pendiente_compras']
            return redirect('creditos_compras:registrar_pagos', compra_id=compra.id)

        transaction_id = 'PAYPAL-' + secrets.token_hex(4).upper()
        for pago in resultados:
            pago.metodo_pago = 'PAYPAL'
            pago.paypal_transaction_id = transaction_id
            pago.save(update_fields=['metodo_pago', 'paypal_transaction_id'])

        request.session['ultimo_lote_pagos_compras'] = [str(p.id) for p in resultados]
        del request.session['paypal_pago_pendiente_compras']
        messages.success(request, f'{len(resultados)} pago(s) registrado(s) correctamente vía PayPal.')
        return redirect('creditos_compras:comprobante_lote')

    return render(request, 'creditos_compras/paypal_confirm.html', {
        'compra': compra, 'filas': filas, 'total': total,
    })


class HistorialPagosListView(LoginRequiredMixin, ListView):
    model = PagoCuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'items'
    paginate_by = 25

    def get_queryset(self):
        qs = PagoCuotaCompra.objects.select_related(
            'cuota', 'cuota__compra', 'cuota__compra__supplier'
        ).all()
        compra_id = self.request.GET.get('compra')
        if compra_id:
            qs = qs.filter(cuota__compra_id=compra_id)
        return qs


@login_required
def imprimir_plan_pagos(request, compra_id):
    compra = get_object_or_404(Purchase, pk=compra_id, tipo_pago='CREDITO')
    return pdf_utils.generar_pdf_plan_pagos(compra)


@login_required
def comprobante_lote(request):
    """Página HTML de confirmación tras registrar uno o varios pagos."""
    ids = request.session.get('ultimo_lote_pagos_compras', [])
    pagos = PagoCuotaCompra.objects.filter(id__in=ids).select_related(
        'cuota', 'cuota__compra', 'cuota__compra__supplier'
    )
    return render(request, 'creditos_compras/comprobante_lote.html', {'pagos': pagos})


@login_required
def comprobante_lote_pdf(request):
    ids = request.session.get('ultimo_lote_pagos_compras', [])
    pagos = PagoCuotaCompra.objects.filter(id__in=ids).select_related(
        'cuota', 'cuota__compra', 'cuota__compra__supplier'
    )
    return pdf_utils.generar_pdf_comprobante_lote(pagos)
