# accounts/middleware.py - VERSION CORRIGÉE
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpResponse
from django.core.cache import cache
from django.conf import settings
from .models import CustomUser
import time


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


class RateLimitMiddleware(MiddlewareMixin):
    """Middleware pour limiter le nombre de requêtes par IP"""
    
    def process_request(self, request):
        # Vérifier si le rate limiting est activé
        if not getattr(settings, 'RATE_LIMIT_ENABLED', False):
            return None
            
        # Obtenir l'IP du client
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Clé de cache pour cette IP
        cache_key = f'rate_limit_{ip}'
        
        # Récupérer les requêtes actuelles
        requests = cache.get(cache_key, [])
        now = time.time()
        
        # Nettoyer les anciennes requêtes (plus vieilles que la fenêtre)
        window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)
        requests = [req_time for req_time in requests if now - req_time < window]
        
        # Vérifier la limite
        max_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)
        if len(requests) >= max_requests:
            return HttpResponse(
                "Trop de requêtes. Veuillez patienter avant de réessayer.",
                status=429,
                content_type='text/plain'
            )
        
        # Ajouter la requête actuelle
        requests.append(now)
        cache.set(cache_key, requests, window)
        
        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Middleware pour ajouter des headers de sécurité"""
    
    def process_response(self, request, response):
        # Headers de sécurité supplémentaires
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # HSTS seulement en HTTPS
        if request.is_secure():
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        return response
