from django.urls import path
from . import views

app_name = 'security'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),

    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),

    path('roles/', views.GroupListView.as_view(), name='group_list'),
    path('roles/create/', views.GroupCreateView.as_view(), name='group_create'),
    path('roles/<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_update'),
    path('roles/<int:pk>/delete/', views.GroupDeleteView.as_view(), name='group_delete'),

    path('permissions/', views.PermissionListView.as_view(), name='permission_list'),
]
