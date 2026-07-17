from django.urls import path
from . import views

app_name = 'creditos_ventas'

urlpatterns = [
    path('cuotas/', views.CuotaVentaListView.as_view(), name='cuota_list'),
    path('cuotas/pendientes/', views.CuotaVentaPendientesListView.as_view(), name='cuotas_pendientes'),
    path('facturas/<int:factura_id>/pagar/', views.registrar_pagos, name='registrar_pagos'),
    path('facturas/<int:factura_id>/pagar/paypal/', views.pagar_con_paypal, name='pagar_con_paypal'),
    path('facturas/<int:factura_id>/pagar/paypal/login/', views.paypal_login, name='paypal_login'),
    path('facturas/<int:factura_id>/pagar/paypal/confirmar/', views.paypal_confirmar, name='paypal_confirmar'),
    path('facturas/<int:factura_id>/plan-pagos/pdf/', views.imprimir_plan_pagos, name='plan_pagos_pdf'),
    path('pagos/historial/', views.HistorialPagosListView.as_view(), name='historial_pagos'),
    path('pagos/comprobante/', views.comprobante_lote, name='comprobante_lote'),
    path('pagos/comprobante/pdf/', views.comprobante_lote_pdf, name='comprobante_lote_pdf'),
]
