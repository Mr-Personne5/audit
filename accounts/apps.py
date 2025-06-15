# accounts/apps.py - VERSION ALTERNATIVE PLUS SÛRE
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Gestion des Comptes'

    def ready(self):
        """Importer les signaux quand l'app est prête"""
        # ✅ Import retardé et sécurisé
        from django.conf import settings
        if settings.configured:
            try:
                from . import signals  # ✅ Import relatif plus sûr
            except ImportError:
                pass
