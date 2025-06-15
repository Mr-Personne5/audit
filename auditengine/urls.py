# auditengine/urls.py
from django.urls import path
from . import views

app_name = 'auditengine'

urlpatterns = [
    # Vues principales
    path('', views.session_list, name='session_list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('create/', views.create_session, name='create_session'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/delete/', views.delete_session, name='delete_session'),

    # Actions de traitement IA
    path('sessions/<int:pk>/process/', views.process_session, name='process_session'),
    path('sessions/<int:pk>/status/', views.session_status, name='session_status'),
    path('sessions/<int:pk>/logs/', views.session_logs, name='session_logs'),

    # Gestion des anomalies
    path('anomalies/<int:pk>/', views.anomalie_detail, name='anomalie_detail'),
    path('anomalies/<int:pk>/correct/', views.corriger_anomalie, name='corriger_anomalie'),

    # Export et analyse
    path('sessions/<int:pk>/export/', views.export_results, name='export_results'),
    path('sessions/<int:pk>/recommendations/', views.generate_recommendations, name='generate_recommendations'),

    # Administration IA
    path('admin/config/', views.parametrage_ia, name='parametrage_ia'),
    path('admin/models/', views.modeles_ia, name='modeles_ia'),
    path('admin/retrain/', views.reentrainer_modeles, name='reentrainer_modeles'),
    path('admin/evaluate/<int:modele_id>/', views.evaluer_modele, name='evaluer_modele'),
    path('admin/corrections-stats/', views.corrections_stats, name='corrections_stats'),

    # API utilitaires
    path('api/paie-files/', views.get_available_paie_files, name='get_available_paie_files'),
]
