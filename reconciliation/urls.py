# reconciliation/urls.py
from django.urls import path
from . import views

app_name = 'reconciliation'

urlpatterns = [
    # Vues principales
    path('', views.session_list, name='session_list'),
    path('create/', views.create_session, name='create_session'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/delete/', views.delete_session, name='delete_session'),

    # Actions de traitement
    path('sessions/<int:pk>/process/', views.process_session, name='process_session'),
    path('sessions/<int:pk>/status/', views.session_status, name='session_status'),
    path('sessions/<int:pk>/logs/', views.session_logs, name='session_logs'),

    # Export et analyse
    path('sessions/<int:pk>/export/', views.export_results, name='export_results'),
    path('sessions/<int:pk>/analysis/', views.detailed_analysis, name='detailed_analysis'),

    # Dashboard et administration
    path('dashboard/', views.analysis_dashboard, name='analysis_dashboard'),
    path('rules/', views.rules_admin, name='rules_admin'),

    # API utilitaires
    path('api/files/', views.get_available_files, name='get_available_files'),
]
