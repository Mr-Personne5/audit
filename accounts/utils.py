import logging
from django.http import HttpRequest
from .models import UserLog

logger = logging.getLogger('auditia')


def log_user_action(user, action, feature, target="", resource_id="",
                    old_value="", new_value="", status="success", request=None):
    """
    Fonction utilitaire pour enregistrer les actions utilisateur
    """
    ip_address = None
    user_agent = ""

    if request and isinstance(request, HttpRequest):
        # Récupérer l'IP réelle même derrière un proxy
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limiter la taille

    # Créer le log en base
    user_log = UserLog.objects.create(
        user=user,
        action=action,
        feature=feature,
        target=target,
        resource_id=resource_id,
        old_value=str(old_value),
        new_value=str(new_value),
        status=status,
        ip_address=ip_address,
        user_agent=user_agent
    )

    # Log également dans le fichier système
    log_data = user_log.to_json()
    logger.info(f"USER_ACTION: {log_data}")

    return user_log


def log_authentication(user, action, status="success", request=None):
    """Log spécifique pour les actions d'authentification"""
    return log_user_action(
        user=user,
        action=action,
        feature="Authentification",
        status=status,
        request=request
    )
