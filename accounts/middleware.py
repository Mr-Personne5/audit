# accounts/middleware.py - VERSION CORRIGÉE
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from .models import CustomUser


class UserActivityMiddleware(MiddlewareMixin):
    """Middleware pour mettre à jour automatiquement l'activité utilisateur"""

    def process_request(self, request):  # ✅ Garder en méthode d'instance (obligatoire pour Django)
        if request.user.is_authenticated and isinstance(request.user, CustomUser):
            # Mettre à jour l'activité seulement toutes les 5 minutes pour éviter trop d'écritures
            now = timezone.now()
            if (not request.user.last_activity or
                    (now - request.user.last_activity).total_seconds() > 300):
                request.user.update_last_activity()
        return None
