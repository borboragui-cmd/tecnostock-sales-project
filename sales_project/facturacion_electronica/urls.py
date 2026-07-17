from django.urls import path
from . import views

app_name = 'facturacion_electronica'

urlpatterns = [
    path('facturas/<int:factura_id>/generar/', views.generar_comprobante_factura, name='generar_factura'),
    path('compras/<int:compra_id>/generar/', views.generar_comprobante_compra, name='generar_compra'),
    path('comprobantes/', views.ComprobanteListView.as_view(), name='comprobante_list'),
    path('comprobantes/<int:pk>/', views.comprobante_detail, name='comprobante_detail'),
    path('comprobantes/<int:pk>/firmar/', views.firmar_comprobante, name='firmar'),
    path('comprobantes/<int:pk>/enviar/', views.enviar_comprobante, name='enviar'),
    path('comprobantes/<int:pk>/consultar/', views.consultar_comprobante, name='consultar'),
]
