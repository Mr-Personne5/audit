from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Tableau de bord
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/advanced/', views.dashboard_advanced, name='dashboard_advanced'),
    path('missions/supervision/', views.mission_supervision, name='mission_supervision'),

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

    # Profil utilisateur
    path('profil/', views.user_profile, name='user_profile'),
    path('parametres/', views.user_settings, name='user_settings'),
    path('mes-logs/', views.user_logs_personal, name='user_logs_personal'),

    # API Admin
    path('api/admin_alerts/', views.admin_alerts_api, name='admin_alerts_api'),

    path('api/dashboard_admin_stats/', views.dashboard_admin_stats_api, name='dashboard_admin_stats_api'),
    path('api/dashboard_user_stats/', views.dashboard_user_stats_api, name='dashboard_user_stats_api'),
    path('api/dashboard_advanced_metrics/', views.dashboard_advanced_metrics_api, name='dashboard_advanced_metrics_api'),
    path('api/mission_supervision_data/', views.mission_supervision_data_api, name='mission_supervision_data_api'),
    path('api/mission_details/<int:mission_id>/', views.mission_details_api, name='mission_details_api'),
    path('api/mission_category_data/<int:mission_id>/<str:category>/', views.mission_category_data_api, name='mission_category_data_api'),
]