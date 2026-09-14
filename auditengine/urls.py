# auditengine/urls.py
from django.urls import path
from . import views
from .views import dashboard_anomalies_stats_api, generate_recommendations

app_name = 'auditengine'

urlpatterns = [
    # Vues principales
    path('', views.session_list, name='session_list'),
    path('tableau_de_bord/', views.dashboard, name='dashboard'),
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
    path('sessions/<int:pk>/recommendations/export_pdf/', views.export_recommendations_pdf, name='export_recommendations_pdf'),

    # Administration IA
    path('admin/config/', views.parametrage_ia, name='parametrage_ia'),
    path('admin/models/', views.modeles_ia, name='modeles_ia'),
    path('admin/retrain/', views.reentrainer_modeles, name='reentrainer_modeles'),
    path('admin/evaluate/<int:modele_id>/', views.evaluer_modele, name='evaluer_modele'),
    path('admin/corrections-stats/', views.corrections_stats, name='corrections_stats'),

    # API utilitaires
    path('api/paie-files/', views.get_available_paie_files, name='get_available_paie_files'),
    path('api/dashboard_stats/', views.dashboard_auditengine_stats_api, name='dashboard_auditengine_stats_api'),
    path('api/session_stats/<int:pk>/', views.api_session_stats, name='api_session_stats'),
    path('api/session_results/<int:pk>/', views.api_session_results, name='api_session_results'),
    path('api/dashboard_anomalies_stats/', dashboard_anomalies_stats_api, name='dashboard_anomalies_stats_api'),
    
    # Validation des résultats
    path('resultats/<int:resultat_id>/valider/', views.valider_resultat, name='valider_resultat'),
    
    # Gestion des tâches d'action
    path('sessions/<int:session_id>/taches/', views.liste_taches_action, name='liste_taches_action'),
    path('sessions/<int:session_id>/creer-taches/', views.creer_taches_action, name='creer_taches_action'),
    path('taches/<int:tache_id>/assigner/', views.assigner_tache, name='assigner_tache'),
    path('taches/<int:tache_id>/marquer-faite/', views.marquer_tache_faite, name='marquer_tache_faite'),
    
    # Sécurité et traçabilité
    path('security/dashboard/', views.security_dashboard, name='security_dashboard'),
    path('security/logs/', views.audit_logs, name='audit_logs'),
]
