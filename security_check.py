#!/usr/bin/env python
"""
Script de vérification de sécurité pour Audit IA
Vérifie que toutes les configurations de sécurité sont en place
"""

import os
import sys
import django
from pathlib import Path

# Configuration Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')

django.setup()

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.cache import cache


def check_security_settings():
    """Vérifie les paramètres de sécurité"""
    print("🔒 Vérification de la configuration de sécurité...")
    
    issues = []
    warnings = []
    
    # Vérification DEBUG
    if settings.DEBUG:
        warnings.append("⚠️  DEBUG=True - Désactivez en production")
    else:
        print("✅ DEBUG=False")
    
    # Vérification SECRET_KEY
    if settings.SECRET_KEY.startswith('django-insecure-'):
        issues.append("❌ SECRET_KEY par défaut - Changez en production")
    else:
        print("✅ SECRET_KEY personnalisée")
    
    # Vérification ALLOWED_HOSTS
    if not settings.ALLOWED_HOSTS or '*' in settings.ALLOWED_HOSTS:
        issues.append("❌ ALLOWED_HOSTS non configuré ou trop permissif")
    else:
        print(f"✅ ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
    
    # Vérification des sessions
    if hasattr(settings, 'SESSION_COOKIE_SECURE') and settings.SESSION_COOKIE_SECURE:
        print("✅ Sessions sécurisées (HTTPS)")
    else:
        warnings.append("⚠️  Sessions non sécurisées")
    
    if hasattr(settings, 'SESSION_COOKIE_HTTPONLY') and settings.SESSION_COOKIE_HTTPONLY:
        print("✅ Sessions HttpOnly")
    else:
        warnings.append("⚠️  Sessions accessibles via JavaScript")
    
    # Vérification CSRF
    if hasattr(settings, 'CSRF_COOKIE_SECURE') and settings.CSRF_COOKIE_SECURE:
        print("✅ CSRF sécurisé")
    else:
        warnings.append("⚠️  CSRF non sécurisé")
    
    # Vérification des headers de sécurité
    security_headers = [
        'SECURE_BROWSER_XSS_FILTER',
        'SECURE_CONTENT_TYPE_NOSNIFF',
        'X_FRAME_OPTIONS'
    ]
    
    for header in security_headers:
        if hasattr(settings, header) and getattr(settings, header):
            print(f"✅ {header} activé")
        else:
            warnings.append(f"⚠️  {header} non configuré")
    
    # Vérification du rate limiting
    if hasattr(settings, 'RATE_LIMIT_ENABLED') and settings.RATE_LIMIT_ENABLED:
        print("✅ Rate limiting activé")
    else:
        warnings.append("⚠️  Rate limiting non activé")
    
    # Vérification des validateurs de mots de passe
    if len(settings.AUTH_PASSWORD_VALIDATORS) >= 4:
        print("✅ Validateurs de mots de passe configurés")
    else:
        warnings.append("⚠️  Validateurs de mots de passe insuffisants")
    
    # Vérification du hachage des mots de passe
    if 'Argon2PasswordHasher' in settings.PASSWORD_HASHERS:
        print("✅ Argon2 activé pour le hachage des mots de passe")
    else:
        warnings.append("⚠️  Argon2 non activé")
    
    return issues, warnings


def check_file_validation():
    """Vérifie la validation des fichiers"""
    print("\n📁 Vérification de la validation des fichiers...")
    
    try:
        from uploads.models import FichierImporte
        
        # Vérifier les validateurs
        field = FichierImporte._meta.get_field('fichier')
        validators = field.validators
        
        if len(validators) >= 3:
            print("✅ Validateurs de fichiers configurés")
        else:
            print("⚠️  Validateurs de fichiers insuffisants")
        
        # Vérifier la taille maximale
        max_size = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
        if max_size <= 50 * 1024 * 1024:  # 50MB
            print(f"✅ Taille maximale des fichiers: {max_size // (1024*1024)}MB")
        else:
            print(f"⚠️  Taille maximale très élevée: {max_size // (1024*1024)}MB")
        
        # Vérifier python-magic
        try:
            import magic
            print("✅ python-magic disponible pour la validation MIME")
        except ImportError:
            print("ℹ️  python-magic non disponible - validation par extension uniquement")
            
    except ImportError as e:
        print(f"⚠️  Impossible de vérifier la validation des fichiers: {e}")


def check_database_security():
    """Vérifie la sécurité de la base de données"""
    print("\n🗄️  Vérification de la sécurité de la base de données...")
    
    db_engine = settings.DATABASES['default']['ENGINE']
    
    if 'sqlite' in db_engine:
        print("⚠️  SQLite utilisé - Considérez PostgreSQL pour la production")
    elif 'postgresql' in db_engine:
        print("✅ PostgreSQL configuré")
    else:
        print(f"ℹ️  Moteur de base de données: {db_engine}")


def check_cache_configuration():
    """Vérifie la configuration du cache"""
    print("\n⚡ Vérification de la configuration du cache...")
    
    cache_backend = settings.CACHES['default']['BACKEND']
    
    if 'redis' in cache_backend:
        print("✅ Redis configuré pour le cache")
    elif 'locmem' in cache_backend:
        print("⚠️  Cache en mémoire locale - Considérez Redis pour la production")
    else:
        print(f"ℹ️  Backend de cache: {cache_backend}")


def test_password_hashing():
    """Teste le hachage des mots de passe"""
    print("\n🔐 Test du hachage des mots de passe...")
    
    test_password = "TestPassword123!"
    hashed = make_password(test_password)
    
    if check_password(test_password, hashed):
        print("✅ Hachage des mots de passe fonctionnel")
        
        # Vérifier l'algorithme utilisé
        if hashed.startswith('argon2'):
            print("✅ Argon2 utilisé pour le hachage")
        elif hashed.startswith('pbkdf2'):
            print("ℹ️  PBKDF2 utilisé pour le hachage")
        else:
            print(f"ℹ️  Algorithme de hachage: {hashed.split('$')[0]}")
    else:
        print("❌ Problème avec le hachage des mots de passe")


def check_middleware_security():
    """Vérifie les middlewares de sécurité"""
    print("\n🛡️  Vérification des middlewares de sécurité...")
    
    security_middlewares = [
        'django.middleware.security.SecurityMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'accounts.middleware.RateLimitMiddleware',
        'accounts.middleware.SecurityHeadersMiddleware',
    ]
    
    for middleware in security_middlewares:
        if middleware in settings.MIDDLEWARE:
            print(f"✅ {middleware.split('.')[-1]} activé")
        else:
            print(f"⚠️  {middleware.split('.')[-1]} non activé")


def main():
    """Fonction principale"""
    print("=" * 60)
    print("🔒 AUDIT DE SÉCURITÉ - AUDIT IA")
    print("=" * 60)
    
    try:
        # Vérifications
        issues, warnings = check_security_settings()
        check_file_validation()
        check_database_security()
        check_cache_configuration()
        check_middleware_security()
        test_password_hashing()
        
        # Résumé
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DE SÉCURITÉ")
        print("=" * 60)
        
        if issues:
            print(f"\n❌ PROBLÈMES CRITIQUES ({len(issues)}):")
            for issue in issues:
                print(f"  {issue}")
        
        if warnings:
            print(f"\n⚠️  AVERTISSEMENTS ({len(warnings)}):")
            for warning in warnings:
                print(f"  {warning}")
        
        if not issues and not warnings:
            print("\n🎉 Configuration de sécurité excellente !")
        elif not issues:
            print(f"\n✅ Configuration correcte avec {len(warnings)} améliorations possibles")
        else:
            print(f"\n🚨 {len(issues)} problème(s) critique(s) à résoudre")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"❌ Erreur lors de la vérification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 