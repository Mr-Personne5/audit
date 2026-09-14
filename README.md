# Audit IA

Application Django d'audit de paie assisté par IA : détection d'anomalies (salaires anormaux, employés fantômes, primes suspectes, heures excessives, RIB dupliqués), rapprochement RH/Paie automatisé et gestion du cycle de vie des recommandations d'audit.

## Fonctionnalités

- **Détection d'anomalies par IA** — pipeline combinant un Isolation Forest (détection) et un classifieur MLP (typage de l'anomalie), avec ré-entraînement à partir des corrections des auditeurs.
- **Rapprochement RH / Paie** — matching par matricule puis par similarité nom/prénom, détection des employés non payés, non déclarés et des doublons de paie.
- **Recommandations & plans d'action** — génération automatique de recommandations à partir des anomalies et rapprochements détectés, suivi de statut, assignation, échéances, KPIs.
- **Import de fichiers** — upload CSV/Excel avec détection et mapping automatique des colonnes, validation du contenu et prévisualisation.
- **Gestion des missions et utilisateurs** — isolation des données par mission d'audit, rôles Admin/Auditeur.
- **Traçabilité** — journal d'actions utilisateur, tableau de bord de sécurité, logs applicatifs.

## Stack technique

- Django 5.2, SQLite (dev) / PostgreSQL (prod)
- pandas, scikit-learn, joblib pour le pipeline IA
- Argon2 pour le hachage des mots de passe, Redis pour le cache/rate limiting en production
- WeasyPrint / xhtml2pdf pour l'export PDF des rapports

## Structure du projet

```
accounts/        Authentification, utilisateurs, missions, rôles, journal d'activité
auditengine/     Moteur de détection d'anomalies IA (Isolation Forest + MLP)
reconciliation/  Moteur de rapprochement RH / Paie
recommendations/ Cycle de vie des recommandations et plans d'action
uploads/         Import, validation et mapping des fichiers CSV/Excel
ml_models/       Modèles IA entraînés (.pkl)
docs/            Documentation technique et fonctionnelle
```

## Installation

```bash
git clone https://github.com/Mr-Personne5/audit.git
cd audit
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r Requirement.txt
```

Copier `env_example.txt` vers `.env` (ou définir les variables d'environnement directement) et renseigner au minimum :

```
SECRET_KEY=...
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

Puis :

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Configuration par environnement

- `audit_ia/settings.py` — configuration par défaut (développement).
- `audit_ia/settings_dev.py` — développement (`--settings=audit_ia.settings_dev`).
- `audit_ia/settings_prod.py` — production : PostgreSQL, cache Redis, cookies sécurisés, HSTS (`--settings=audit_ia.settings_prod`).

## Sécurité

Voir [SECURITY.md](SECURITY.md) pour le détail des mesures de sécurité mises en place et la checklist de déploiement.
