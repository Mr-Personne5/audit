# 🔒 Guide de Sécurité - Audit IA

## Vue d'ensemble

Ce document décrit les mesures de sécurité implémentées dans l'application Audit IA et les bonnes pratiques à suivre.

## 🛡️ Couches de Sécurité Implémentées

### 1. Authentification & Autorisation
- ✅ Authentification obligatoire sur toutes les vues (`@login_required`)
- ✅ Système de rôles (Admin/Auditeur) avec `@user_passes_test`
- ✅ Modèle utilisateur personnalisé avec permissions granulaires
- ✅ Sessions sécurisées avec expiration automatique

### 2. Protection CSRF
- ✅ Middleware CSRF activé
- ✅ Tokens CSRF sur tous les formulaires
- ✅ Headers CSRF dans les requêtes AJAX
- ✅ Cookies CSRF sécurisés en production

### 3. Validation des Fichiers
- ✅ Extensions autorisées uniquement (`.csv`, `.xlsx`, `.xls`)
- ✅ Validation du contenu MIME avec `python-magic`
- ✅ Limite de taille (30MB max)
- ✅ Limite quotidienne d'uploads par utilisateur (50 en dev, 20 en prod)

### 4. Isolation des Données
- ✅ Séparation par mission d'audit
- ✅ Permissions granulaires sur les fichiers
- ✅ Contraintes d'unicité en base de données

### 5. Traçabilité & Audit
- ✅ Logs complets avec IP et user-agent
- ✅ Middleware de suivi d'activité utilisateur
- ✅ Historique des modifications

### 6. Headers de Sécurité
- ✅ X-Frame-Options: DENY
- ✅ X-Content-Type-Options: nosniff
- ✅ X-XSS-Protection: 1; mode=block
- ✅ HSTS en production
- ✅ Referrer-Policy: strict-origin-when-cross-origin

### 7. Rate Limiting
- ✅ Limitation des requêtes par IP
- ✅ Protection contre les attaques par force brute
- ✅ Configuration flexible (100 req/min en dev, 60 en prod)

### 8. Hachage des Mots de Passe
- ✅ Argon2 (plus sécurisé que PBKDF2)
- ✅ Validation stricte des mots de passe
- ✅ Longueur minimale configurable

## 🚀 Configuration de Production

### Variables d'Environnement Requises

```bash
# Sécurité critique
SECRET_KEY=votre_cle_secrete_tres_longue_et_complexe_ici
DEBUG=False
ALLOWED_HOSTS=votre-domaine.com,www.votre-domaine.com

# Base de données PostgreSQL
DB_NAME=audit_ia
DB_USER=audit_user
DB_PASSWORD=votre_mot_de_passe_db
DB_HOST=localhost
DB_PORT=5432

# Cache Redis
REDIS_URL=redis://127.0.0.1:6379/1

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=votre_email@gmail.com
EMAIL_HOST_PASSWORD=votre_mot_de_passe_app
DEFAULT_FROM_EMAIL=noreply@votre-domaine.com
```

### Installation des Dépendances

```bash
pip install -r requirements_security.txt
```

### Lancement en Production

```bash
python manage.py runserver --settings=audit_ia.settings_prod
```

## 🔍 Vérification de Sécurité

### Script Automatique

```bash
python security_check.py
```

Ce script vérifie :
- Configuration des paramètres de sécurité
- Validation des fichiers
- Configuration de la base de données
- Hachage des mots de passe
- Headers de sécurité

### Vérifications Manuelles

1. **Test des Headers de Sécurité**
   ```bash
   curl -I https://votre-domaine.com
   ```

2. **Test du Rate Limiting**
   ```bash
   # Faire 100+ requêtes rapides et vérifier le blocage
   ```

3. **Test de la Validation des Fichiers**
   - Essayer d'uploader un fichier avec une mauvaise extension
   - Essayer d'uploader un fichier trop volumineux
   - Essayer d'uploader un fichier avec un contenu malveillant

## 📋 Checklist de Déploiement

### Avant le Déploiement
- [ ] Variables d'environnement configurées
- [ ] Base de données PostgreSQL installée
- [ ] Redis installé et configuré
- [ ] Certificat SSL installé
- [ ] Firewall configuré
- [ ] Sauvegardes automatisées

### Après le Déploiement
- [ ] Script de sécurité exécuté
- [ ] Tests de pénétration basiques effectués
- [ ] Monitoring de sécurité configuré
- [ ] Logs de sécurité surveillés
- [ ] Mots de passe des utilisateurs changés

## 🚨 Réponse aux Incidents

### En Cas de Compromission

1. **Isoler le système**
   - Désactiver l'accès externe
   - Sauvegarder les logs

2. **Analyser l'incident**
   - Examiner les logs de sécurité
   - Identifier le vecteur d'attaque
   - Évaluer l'étendue des dégâts

3. **Corriger les vulnérabilités**
   - Appliquer les correctifs
   - Renforcer la sécurité
   - Changer les mots de passe

4. **Restaurer le service**
   - Tester la sécurité
   - Remettre en ligne progressivement
   - Surveiller les activités suspectes

### Contacts d'Urgence

- **Administrateur système** : [contact]
- **Responsable sécurité** : [contact]
- **Support technique** : [contact]

## 📚 Ressources

- [Documentation Django Security](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Guide de sécurité Python](https://python-security.readthedocs.io/)

## 🔄 Mises à Jour de Sécurité

### Procédure de Mise à Jour

1. **Planifier la maintenance**
2. **Sauvegarder les données**
3. **Tester en environnement de staging**
4. **Appliquer les mises à jour**
5. **Vérifier la sécurité**
6. **Documenter les changements**

### Surveillance Continue

- Monitoring des logs de sécurité
- Surveillance des tentatives d'intrusion
- Mise à jour régulière des dépendances
- Audit de sécurité périodique

---

**Dernière mise à jour** : [Date]
**Version** : 1.0
**Responsable** : [Nom] 