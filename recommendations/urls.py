# recommendations/urls.py - CORRIGER les noms de fonctions

from django.urls import path
from . import views

app_name = 'recommendations'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # CRUD Recommandations

    path('list/', views.list_recommandations, name='list'),
    path('create/', views.create_recommandation, name='create'),
    path('<int:pk>/', views.detail_recommandation, name='detail'),
    path('<int:pk>/edit/', views.edit_recommandation, name='edit'),
    path('<int:pk>/delete/', views.delete_recommandation, name='delete'),
    path('<int:pk>/assign/', views.assign_recommandation, name='assign'),
    # Actions AJAX
    path('<int:pk>/change-status/', views.change_status_recommandation, name='change_status'),

    # Plan d'action
    path('<int:recommandation_pk>/action/create/', views.create_action_plan, name='action_create'),
    path('action/<int:pk>/update-progress/', views.update_progress_action_plan, name='action_update_progress'),

    # Génération automatique - ✅ CORRIGER le nom
    path('generate/audit/<int:session_audit_id>/', views.generate_recommendations_audit, name='generate_audit'),

    # Export et rapports - ✅ CORRIGER le nom
    path('export/', views.export_recommendations, name='export'),

    # API - ✅ CORRIGER le nom
    path('api/stats/', views.api_stats_recommendations, name='api_stats'),

    path('api/dashboard_stats/', views.dashboard_recommendations_stats_api, name='dashboard_recommendations_stats_api'),
]
