"""
Configuration de développement pour audit_ia.
Utilisez ce fichier en développement avec: python manage.py runserver --settings=audit_ia.settings_dev
"""

from .settings import *

# ==================== CONFIGURATION DÉVELOPPEMENT ====================

# Sécurité adaptée au développement
DEBUG = True
SECRET_KEY = 'audit_ia_dev_2024_secure_key_very_long_and_complex_for_development_only'
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Sessions adaptées au développement (HTTP)
SESSION_COOKIE_SECURE = False  # HTTP en développement
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 3600  # 1 heure

# CSRF adapté au développement
CSRF_COOKIE_SECURE = False  # HTTP en développement
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Headers de sécurité (sans HSTS en développement)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 0  # Pas de HSTS en développement
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = 'DENY'

# Rate limiting plus permissif en développement
RATE_LIMIT_REQUESTS = 100  # 100 requêtes par minute
RATE_LIMIT_WINDOW = 60

# Validation des mots de passe (plus permissive en développement)
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 6,  # Plus permissif en développement
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Limite d'uploads plus permissive en développement
UPLOAD_LIMIT_DAILY = 50  # 50 uploads par jour

# Logging de développement
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',  # Plus de logs en développement
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'audit_logs.log',
            'formatter': 'detailed',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
        },
    },
    'loggers': {
        'auditia': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django.security': {
            'handlers': ['file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
} 