from django.urls import path
from . import views

app_name = 'creditos_compras'

urlpatterns = [
    path('cuotas/', views.CuotaCompraListView.as_view(), name='cuota_list'),
    path('cuotas/pendientes/', views.CuotaCompraPendientesListView.as_view(), name='cuotas_pendientes'),
    path('compras/<int:compra_id>/pagar/', views.registrar_pagos, name='registrar_pagos'),
    path('compras/<int:compra_id>/pagar/paypal/', views.pagar_con_paypal, name='pagar_con_paypal'),
    path('compras/<int:compra_id>/pagar/paypal/login/', views.paypal_login, name='paypal_login'),
    path('compras/<int:compra_id>/pagar/paypal/confirmar/', views.paypal_confirmar, name='paypal_confirmar'),
    path('compras/<int:compra_id>/plan-pagos/pdf/', views.imprimir_plan_pagos, name='plan_pagos_pdf'),
    path('pagos/historial/', views.HistorialPagosListView.as_view(), name='historial_pagos'),
    path('pagos/comprobante/', views.comprobante_lote, name='comprobante_lote'),
    path('pagos/comprobante/pdf/', views.comprobante_lote_pdf, name='comprobante_lote_pdf'),
]
