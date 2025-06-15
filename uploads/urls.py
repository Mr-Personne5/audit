from django.urls import path
from . import views

app_name = 'uploads'

urlpatterns = [
    # ==================== VUES PRINCIPALES ====================

    # Liste des fichiers
    path('', views.upload_list, name='upload_list'),
    path('list/', views.upload_list, name='upload_list_alt'),

    # Upload de fichier
    path('upload/', views.upload_file, name='upload_file'),

    # Détail d'un fichier
    path('file/<int:pk>/', views.file_detail, name='file_detail'),

    # Suppression d'un fichier
    path('file/<int:pk>/delete/', views.delete_file, name='delete_file'),

    # Approbation d'un fichier (admin seulement)
    path('file/<int:pk>/approve/', views.approve_file, name='approve_file'),

    # Statistiques (admin seulement)
    path('stats/', views.upload_stats, name='upload_stats'),

    # ==================== VUES AJAX/API ====================

    # Retraitement d'un fichier
    path('reprocess/<int:pk>/', views.reprocess_file, name='reprocess_file'),

    # Prévisualisation des données
    path('preview/<int:pk>/', views.preview_data, name='preview_data'),

    # Mapping des colonnes
    path('mapping/<int:pk>/', views.mapping_columns, name='mapping_columns'),

    # ==================== VUES ADDITIONNELLES ====================

    # Export de données (à implémenter)
    path('export/<int:pk>/', views.export_file_data, name='export_file_data'),

    # Historique d'un fichier
    path('file/<int:pk>/history/', views.file_history, name='file_history'),

    # Validation en lot (admin)
    path('bulk-approve/', views.bulk_approve, name='bulk_approve'),

    # Téléchargement direct du fichier
    path('download/<int:pk>/', views.download_file, name='download_file'),

    # ==================== VUES DE GESTION ====================

    # Nettoyage des fichiers orphelins (admin)
    path('cleanup/', views.cleanup_files, name='cleanup_files'),

    # Rapport d'utilisation de l'espace (admin)
    path('storage-report/', views.storage_report, name='storage_report'),

    # Migration de fichiers (admin)
    path('migrate/', views.migrate_files, name='migrate_files'),
]
