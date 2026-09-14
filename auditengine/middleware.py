import logging
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from .models import AuditLog

logger = logging.getLogger(__name__)


class SecurityMiddleware(MiddlewareMixin):
    """Middleware pour capturer les informations de sécurité et de traçabilité"""
    
    def process_request(self, request):
        """Capture les informations de la requête"""
        # Stocker les informations de sécurité dans la requête
        request.security_info = {
            'ip_address': self._get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'session_id': request.session.session_key or '',
            'timestamp': timezone.now(),
        }
        
        # Log de connexion si utilisateur authentifié
        if hasattr(request, 'user') and request.user.is_authenticated:
            self._log_user_access(request)
    
    def process_response(self, request, response):
        """Capture les informations de la réponse"""
        # Log des erreurs 4xx et 5xx
        if response.status_code >= 400:
            self._log_error_response(request, response)
        
        return response
    
    def process_exception(self, request, exception):
        """Capture les exceptions"""
        self._log_exception(request, exception)
        return None
    
    def _get_client_ip(self, request):
        """Récupère l'adresse IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _log_user_access(self, request):
        """Log l'accès utilisateur"""
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                AuditLog.log_action(
                    user=request.user,
                    action='login',
                    feature='Security',
                    target='system',
                    ip_address=request.security_info['ip_address'],
                    user_agent=request.security_info['user_agent'],
                    session_id=request.security_info['session_id'],
                    description=f"Accès depuis {request.security_info['ip_address']}",
                    severity='info'
                )
        except Exception as e:
            logger.error(f"Erreur lors du log d'accès: {str(e)}")
    
    def _log_error_response(self, request, response):
        """Log les réponses d'erreur"""
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                severity = 'error' if response.status_code >= 500 else 'warning'
                
                AuditLog.log_action(
                    user=request.user,
                    action='error',
                    feature='Security',
                    target='system',
                    ip_address=request.security_info['ip_address'],
                    user_agent=request.security_info['user_agent'],
                    session_id=request.security_info['session_id'],
                    description=f"Erreur HTTP {response.status_code} pour {request.path}",
                    severity=severity
                )
        except Exception as e:
            logger.error(f"Erreur lors du log d'erreur: {str(e)}")
    
    def _log_exception(self, request, exception):
        """Log les exceptions"""
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                AuditLog.log_action(
                    user=request.user,
                    action='error',
                    feature='Security',
                    target='system',
                    ip_address=request.security_info['ip_address'],
                    user_agent=request.security_info['user_agent'],
                    session_id=request.security_info['session_id'],
                    description=f"Exception: {str(exception)} pour {request.path}",
                    severity='critical'
                )
        except Exception as e:
            logger.error(f"Erreur lors du log d'exception: {str(e)}")


class PermissionMiddleware(MiddlewareMixin):
    """Middleware pour vérifier les permissions et log les accès refusés"""
    
    def process_request(self, request):
        """Vérifie les permissions avant traitement"""
        # Vérification des permissions pour les vues sensibles
        if self._is_sensitive_view(request):
            if not self._has_permission(request):
                self._log_access_denied(request)
                return None
        
        return None
    
    def _is_sensitive_view(self, request):
        """Détermine si la vue est sensible"""
        sensitive_patterns = [
            '/auditengine/sessions/',
            '/auditengine/anomalies/',
            '/auditengine/recommendations/',
            '/admin/',
        ]
        
        return any(pattern in request.path for pattern in sensitive_patterns)
    
    def _has_permission(self, request):
        """Vérifie si l'utilisateur a les permissions nécessaires"""
        # Vérification de base d'authentification
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return False
        
        # Vérifications spécifiques selon la vue
        if '/admin/' in request.path:
            return request.user.is_staff
        
        # Pour les autres vues, vérifier les permissions métier
        return True
    
    def _log_access_denied(self, request):
        """Log les accès refusés"""
        try:
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                AuditLog.log_action(
                    user=user,
                    action='access_denied',
                    feature='Security',
                    target='permission',
                    ip_address=getattr(request, 'security_info', {}).get('ip_address', ''),
                    user_agent=getattr(request, 'security_info', {}).get('user_agent', ''),
                    session_id=getattr(request, 'security_info', {}).get('session_id', ''),
                    description=f"Accès refusé à {request.path}",
                    severity='warning'
                )
        except Exception as e:
            logger.error(f"Erreur lors du log d'accès refusé: {str(e)}")

