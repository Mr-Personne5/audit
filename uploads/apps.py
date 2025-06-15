from django.apps import AppConfig


class UploadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'uploads'
    verbose_name = 'Gestion des fichiers'

    def ready(self):
        # Import des signals si nécessaire
        try:
            import uploads.signals
        except ImportError:
            pass
