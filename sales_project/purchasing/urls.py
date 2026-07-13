from django.urls import path
from . import views

app_name = 'purchasing'

urlpatterns = [
    path('', views.purchase_list, name='purchase_list'),
    path('create/', views.purchase_create, name='purchase_create'),
    path('report/', views.purchase_report, name='purchase_report'),
    path('export/excel/', views.purchase_list_excel, name='purchase_list_excel'),
    path('<int:pk>/', views.purchase_detail, name='purchase_detail'),
    path('<int:pk>/pdf/', views.purchase_pdf, name='purchase_pdf'),
    path('<int:pk>/excel/', views.purchase_excel, name='purchase_excel'),
    path('<int:pk>/delete/', views.purchase_delete, name='purchase_delete'),
]
