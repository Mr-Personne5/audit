from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Gestion des utilisateurs
    path('utilisateurs/', views.user_list, name='user_list'),
    path('utilisateurs/nouveau/', views.user_create, name='user_create'),
    path('utilisateurs/<int:user_id>/modifier/', views.user_edit, name='user_edit'),
    path('utilisateurs/<int:user_id>/supprimer/', views.user_delete, name='user_delete'),

    # Gestion des missions
    path('missions/', views.mission_list, name='mission_list'),
    path('missions/nouvelle/', views.mission_create, name='mission_create'),
    path('missions/<int:mission_id>/modifier/', views.mission_edit, name='mission_edit'),
    path('missions/<int:mission_id>/supprimer/', views.mission_delete, name='mission_delete'),

    # Logs
    path('logs/', views.logs_view, name='logs'),
]