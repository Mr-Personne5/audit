# recommendations/engine.py - CORRIGER les imports et méthodes manquantes

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from django.utils import timezone
from django.db.models import Count, Q  # ✅ AJOUTER Q
from collections import defaultdict

from .models import Recommandation, KPIRecommandation
# CORRIGER : Utiliser get_model pour éviter imports circulaires
from django.apps import apps
from accounts.models import Mission
from accounts.models import CustomUser as User  # ✅ CORRIGER l'import User

logger = logging.getLogger('auditia.recommendations')


class RecommendationEngine:
    """Moteur de génération automatique de recommandations"""

    def __init__(self, mission: Mission, user: User):
        self.mission = mission
        self.user = user
        self.recommandations_generees = []

    def generer_recommandations_audit(self, session_audit) -> List[Recommandation]:  # ✅ Enlever le type hint
        """Génère des recommandations basées sur une session d'audit IA"""
        logger.info(f"Génération recommandations pour session audit {session_audit.id}")

        recommandations = []

        # 1. Recommandations par anomalies critiques
        anomalies_critiques = session_audit.resultats.filter(
            niveau_risque='critique',
            est_anomalie=True
        )

        for anomalie in anomalies_critiques:
            reco = self._creer_recommandation_anomalie_critique(anomalie, session_audit)
            if reco:
                recommandations.append(reco)

        # 2. Recommandations par patterns d'anomalies
        patterns = self._analyser_patterns_anomalies(session_audit)
        for pattern_type, count in patterns.items():
            if count >= 3:  # Seuil pour considérer un pattern
                reco = self._creer_recommandation_pattern(pattern_type, count, session_audit)
                if reco:
                    recommandations.append(reco)

        # 3. Recommandations préventives
        reco_preventive = self._creer_recommandation_preventive_audit(session_audit)
        if reco_preventive:
            recommandations.append(reco_preventive)

        # Sauvegarde en lot
        for reco in recommandations:
            reco.save()

        logger.info(f"{len(recommandations)} recommandations générées depuis audit")
        return recommandations

    def generer_recommandations_rapprochement(self, session_rapprochement) -> List[
        Recommandation]:  # ✅ Enlever le type hint
        """Génère des recommandations basées sur une session de rapprochement"""
        logger.info(f"Génération recommandations pour rapprochement {session_rapprochement.id}")

        recommandations = []

        # 1. Recommandations pour employés non payés
        if session_rapprochement.nb_non_payes > 0:
            reco = self._creer_recommandation_non_payes(session_rapprochement)
            if reco:
                recommandations.append(reco)

        # 2. Recommandations pour employés non déclarés
        if session_rapprochement.nb_non_declares > 0:
            reco = self._creer_recommandation_non_declares(session_rapprochement)
            if reco:
                recommandations.append(reco)

        # 3. Recommandations pour améliorer taux rapprochement
        taux = session_rapprochement.get_taux_rapprochement()
        if taux < 90:  # Seuil d'amélioration
            reco = self._creer_recommandation_amelioration_rapprochement(session_rapprochement, taux)
            if reco:
                recommandations.append(reco)

        # Sauvegarde
        for reco in recommandations:
            reco.save()

        logger.info(f"{len(recommandations)} recommandations générées depuis rapprochement")
        return recommandations

    def generer_recommandations_preventives(self) -> List[Recommandation]:
        """Génère des recommandations préventives basées sur l'historique"""
        logger.info("Génération recommandations préventives")

        recommandations = []

        # 1. Analyse des anomalies récurrentes (30 derniers jours)
        date_limite = timezone.now() - timedelta(days=30)

        # Utiliser get_model pour éviter l'import circulaire
        ResultatAudit = apps.get_model('auditengine', 'ResultatAudit')

        # Grouper par type d'anomalie
        anomalies_recurrentes = ResultatAudit.objects.filter(
            session__mission=self.mission,
            session__date_creation__gte=date_limite,
            est_anomalie=True
        ).values('type_anomalie').annotate(
            count=Count('id')
        ).filter(count__gte=5)  # Au moins 5 occurrences

        for anomalie_data in anomalies_recurrentes:
            reco = self._creer_recommandation_formation_preventive(
                anomalie_data['type_anomalie'],
                anomalie_data['count']
            )
            if reco:
                recommandations.append(reco)

        # 2. Recommandations d'amélioration processus
        reco_processus = self._creer_recommandation_amelioration_processus()
        if reco_processus:
            recommandations.append(reco_processus)

        # Sauvegarde
        for reco in recommandations:
            reco.save()

        logger.info(f"{len(recommandations)} recommandations préventives générées")
        return recommandations

    # ✅ AJOUTER toutes les méthodes privées manquantes

    def _analyser_patterns_anomalies(self, session_audit) -> Dict[str, int]:
        """Analyse les patterns d'anomalies dans une session"""
        patterns = defaultdict(int)

        anomalies = session_audit.resultats.filter(est_anomalie=True)

        for anomalie in anomalies:
            patterns[anomalie.type_anomalie] += 1

        return dict(patterns)

    def _creer_recommandation_anomalie_critique(self, anomalie, session_audit) -> Optional[Recommandation]:
        """Crée une recommandation pour une anomalie critique"""

        # Éviter les doublons
        if Recommandation.objects.filter(
                anomalie_liee=anomalie,
                statut__in=['pending', 'approved', 'assigned', 'in_progress']
        ).exists():
            return None

        # Déterminer le type et la priorité selon l'anomalie
        type_reco, priorite = self._determiner_type_priorite_anomalie(anomalie)

        titre = f"Action corrective - {anomalie.type_anomalie.replace('_', ' ').title()}"

        # ✅ CORRIGER selon les champs réels de votre modèle ResultatAudit
        description = f"""Anomalie critique détectée par l'IA.

**Détails de l'anomalie :**
- Type : {anomalie.get_type_anomalie_display() if hasattr(anomalie, 'get_type_anomalie_display') else anomalie.type_anomalie}
- Niveau de risque : {anomalie.get_niveau_risque_display() if hasattr(anomalie, 'get_niveau_risque_display') else anomalie.niveau_risque}

**Action recommandée :**
{getattr(anomalie, 'recommandation_auto', 'Analyser et corriger cette anomalie')}

**Session d'audit :** {session_audit.nom_session}
"""

        # Calculer échéance selon la priorité
        echeance = self._calculer_echeance(priorite)

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation=type_reco,
            priorite=priorite,
            source='auto_audit',
            mission=self.mission,
            anomalie_liee=anomalie,
            session_audit_liee=session_audit,
            cree_par=self.user,
            date_echeance=echeance,
            impact_estime='fort' if priorite in ['critique', 'haute'] else 'moyen',
            donnees_contexte={
                'generation_auto': True,
                'source_anomalie_id': anomalie.id
            },
            tags=['anomalie_critique', 'ia_detectee', anomalie.type_anomalie]
        )

    def _creer_recommandation_pattern(self, pattern_type: str, count: int, session_audit) -> Optional[Recommandation]:
        """Crée une recommandation basée sur un pattern d'anomalies"""

        titre = f"Formation préventive - Pattern {pattern_type} détecté"
        description = f"""Pattern d'anomalies récurrentes détecté par l'analyse IA.

**Statistiques :**
- Type d'anomalie : {pattern_type.replace('_', ' ').title()}
- Nombre d'occurrences : {count}
- Session d'audit : {session_audit.nom_session}

**Actions recommandées :**
1. Analyser les causes racines de ces anomalies récurrentes
2. Former l'équipe concernée sur les bonnes pratiques
3. Revoir les procédures liées à {pattern_type.replace('_', ' ')}
4. Mettre en place des contrôles préventifs
"""

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='formation',
            priorite='moyenne',
            source='auto_pattern',
            mission=self.mission,
            session_audit_liee=session_audit,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=30),
            impact_estime='moyen',
            donnees_contexte={
                'pattern_type': pattern_type,
                'occurrences': count,
                'session_id': session_audit.id,
                'generation_auto': True
            },
            tags=['pattern', 'formation', 'preventif', pattern_type]
        )

    def _creer_recommandation_preventive_audit(self, session_audit) -> Optional[Recommandation]:
        """Crée une recommandation préventive générale"""

        stats = session_audit.resultats.aggregate(
            total=Count('id'),
            anomalies=Count('id', filter=Q(est_anomalie=True)),
            critiques=Count('id', filter=Q(niveau_risque='critique'))
        )

        taux_anomalies = (stats['anomalies'] / stats['total'] * 100) if stats['total'] > 0 else 0

        if taux_anomalies < 5:  # Taux acceptable
            return None

        titre = f"Amélioration processus - Taux d'anomalies élevé ({taux_anomalies:.1f}%)"
        description = f"""Le taux d'anomalies détectées suggère des améliorations possibles.

**Statistiques de la session :**
- Total d'employés analysés : {stats['total']}
- Anomalies détectées : {stats['anomalies']} ({taux_anomalies:.1f}%)
- Anomalies critiques : {stats['critiques']}

**Recommandations :**
1. Revoir les processus de saisie et validation de la paie
2. Renforcer les contrôles qualité avant traitement
3. Former les équipes sur les points de vigilance identifiés
4. Mettre en place des alertes préventives
"""

        priorite = 'haute' if taux_anomalies > 15 else 'moyenne'

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='amelioration',
            priorite=priorite,
            source='auto_audit',
            mission=self.mission,
            session_audit_liee=session_audit,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=45),
            impact_estime='fort' if taux_anomalies > 15 else 'moyen',
            donnees_contexte={
                'taux_anomalies': taux_anomalies,
                'stats': stats,
                'generation_auto': True
            },
            tags=['amelioration', 'processus', 'preventif']
        )

    def _creer_recommandation_non_payes(self, session_rapprochement) -> Optional[Recommandation]:
        """Recommandation pour employés non payés"""

        titre = f"Action corrective - {session_rapprochement.nb_non_payes} employé(s) non payé(s)"
        description = f"""Employés présents en RH mais non payés détectés lors du rapprochement.

**Détails :**
- Session de rapprochement : {session_rapprochement.nom_session}
- Nombre d'employés concernés : {session_rapprochement.nb_non_payes}

**Actions urgentes requises :**
1. Vérifier la liste des employés non payés
2. Identifier les causes (congé, arrêt, erreur de saisie, etc.)
3. Procéder aux régularisations nécessaires
4. Documenter les justifications pour audit
"""

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='correctif',
            priorite='critique',
            source='auto_reconciliation',
            mission=self.mission,
            session_rapprochement_liee=session_rapprochement,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=7),
            impact_estime='critique',
            donnees_contexte={
                'nb_non_payes': session_rapprochement.nb_non_payes,
                'session_id': session_rapprochement.id,
                'generation_auto': True
            },
            tags=['urgent', 'non_paye', 'rapprochement']
        )

    def _creer_recommandation_non_declares(self, session_rapprochement) -> Optional[Recommandation]:
        """Recommandation pour employés payés mais non déclarés"""

        titre = f"Investigation - {session_rapprochement.nb_non_declares} employé(s) payé(s) non déclaré(s)"
        description = f"""Employés payés mais absents de la liste RH - Risque de fraude potentiel.

**Détails :**
- Session de rapprochement : {session_rapprochement.nom_session}
- Nombre d'employés concernés : {session_rapprochement.nb_non_declares}

**⚠️ Actions d'investigation urgentes :**
1. Identifier tous les employés payés non déclarés en RH
2. Vérifier la légitimité de ces paiements
3. Contrôler les autorisations et validations
4. Documenter les justifications ou signaler les anomalies
5. Mettre en place des contrôles préventifs
"""

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='controle',
            priorite='critique',
            source='auto_reconciliation',
            mission=self.mission,
            session_rapprochement_liee=session_rapprochement,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=3),
            impact_estime='critique',
            donnees_contexte={
                'nb_non_declares': session_rapprochement.nb_non_declares,
                'session_id': session_rapprochement.id,
                'risque_fraude': True,
                'generation_auto': True
            },
            tags=['urgent', 'fraude_potentielle', 'investigation', 'rapprochement']
        )

    def _creer_recommandation_amelioration_rapprochement(self, session_rapprochement, taux: float) -> Optional[
        Recommandation]:
        """Recommandation pour améliorer le taux de rapprochement"""

        titre = f"Amélioration processus - Taux de rapprochement faible ({taux:.1f}%)"
        description = f"""Le taux de rapprochement obtenu suggère des améliorations possibles.

**Statistiques :**
- Taux de rapprochement : {taux:.1f}%
- Matches parfaits : {session_rapprochement.nb_matches_parfaits}
- Matches partiels : {session_rapprochement.nb_matches_partiels}

**Recommandations d'amélioration :**
1. Standardiser les formats de données (noms, prénoms, matricules)
2. Améliorer la qualité des données sources
3. Former les équipes sur la saisie des informations
4. Mettre en place des contrôles qualité en amont
5. Automatiser davantage le processus de rapprochement
"""

        priorite = 'haute' if taux < 70 else 'moyenne'

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='amelioration',
            priorite=priorite,
            source='auto_reconciliation',
            mission=self.mission,
            session_rapprochement_liee=session_rapprochement,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=30),
            impact_estime='moyen',
            donnees_contexte={
                'taux_rapprochement': taux,
                'generation_auto': True
            },
            tags=['amelioration', 'rapprochement', 'qualite_donnees']
        )

    def _creer_recommandation_formation_preventive(self, type_anomalie: str, occurrences: int) -> Optional[
        Recommandation]:
        """Crée une recommandation de formation préventive"""

        titre = f"Formation préventive - {type_anomalie.replace('_', ' ').title()} ({occurrences} cas)"
        description = f"""Formation recommandée suite à la détection d'anomalies récurrentes.

**Analyse :**
- Type d'anomalie : {type_anomalie.replace('_', ' ').title()}
- Nombre d'occurrences (30 derniers jours) : {occurrences}
- Tendance : Récurrent

**Objectifs de la formation :**
1. Sensibiliser aux bonnes pratiques
2. Prévenir la récurrence de ces anomalies
3. Améliorer la qualité des processus
4. Réduire les risques d'erreur
"""

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='formation',
            priorite='moyenne',
            source='auto_pattern',
            mission=self.mission,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=45),
            impact_estime='moyen',
            donnees_contexte={
                'type_anomalie': type_anomalie,
                'occurrences': occurrences,
                'generation_auto': True
            },
            tags=['formation', 'preventif', type_anomalie, 'recurrent']
        )

    def _creer_recommandation_amelioration_processus(self) -> Optional[Recommandation]:
        """Recommandation générale d'amélioration des processus"""

        # Vérifier s'il n'y en a pas déjà une récente
        if Recommandation.objects.filter(
                mission=self.mission,
                type_recommandation='amelioration',
                tags__contains=['processus_general'],
                date_creation__gte=timezone.now() - timedelta(days=90)
        ).exists():
            return None

        titre = "Amélioration continue - Optimisation des processus d'audit"
        description = """Recommandation d'amélioration continue des processus d'audit.

**Objectifs :**
1. Optimiser les flux de travail existants
2. Automatiser davantage les contrôles
3. Améliorer la traçabilité des actions
4. Renforcer la documentation des procédures

**Actions suggérées :**
- Révision trimestrielle des processus
- Mise à jour des guides utilisateurs
- Formation continue des équipes
- Analyse des retours d'expérience
"""

        return Recommandation(
            titre=titre,
            description=description,
            type_recommandation='amelioration',
            priorite='basse',
            source='auto_pattern',
            mission=self.mission,
            cree_par=self.user,
            date_echeance=timezone.now().date() + timedelta(days=90),
            impact_estime='moyen',
            donnees_contexte={
                'type': 'amelioration_continue',
                'generation_auto': True
            },
            tags=['amelioration', 'processus_general', 'continue']
        )

    def _determiner_type_priorite_anomalie(self, anomalie) -> tuple:
        """Détermine le type et la priorité d'une recommandation selon l'anomalie"""

        # Mapping type d'anomalie -> type recommandation
        type_mapping = {
            'salaire_anormal': 'correctif',
            'donnees_manquantes': 'correctif',
            'doublon_employe': 'correctif',
            'calcul_errone': 'correctif',
            'donnees_incoherentes': 'correctif',
            'default': 'correctif'
        }

        # Mapping niveau de risque -> priorité
        priorite_mapping = {
            'critique': 'critique',
            'eleve': 'haute',
            'moyen': 'moyenne',
            'faible': 'basse'
        }

        type_reco = type_mapping.get(anomalie.type_anomalie, 'correctif')
        priorite = priorite_mapping.get(getattr(anomalie, 'niveau_risque', 'moyen'), 'moyenne')

        return type_reco, priorite

    def _calculer_echeance(self, priorite: str) -> datetime.date:
        """Calcule l'échéance selon la priorité"""

        delais = {
            'critique': 3,  # 3 jours
            'haute': 7,  # 1 semaine
            'moyenne': 30,  # 1 mois
            'basse': 60  # 2 mois
        }

        jours = delais.get(priorite, 30)
        return timezone.now().date() + timedelta(days=jours)


# ✅ AJOUTER les autres classes manquantes

class KPICalculator:
    """Calculateur de KPIs pour les recommandations"""

    def __init__(self, mission: Mission):
        self.mission = mission

    def calculer_kpis_periode(self, date_debut: datetime.date, date_fin: datetime.date) -> KPIRecommandation:
        """Calcule les KPIs pour une période donnée"""

        # Récupérer les recommandations de la période
        recommandations = Recommandation.objects.filter(
            mission=self.mission,
            date_creation__date__range=[date_debut, date_fin]
        )

        # Calculer les compteurs
        kpi = KPIRecommandation(
            mission=self.mission,
            periode_debut=date_debut,
            periode_fin=date_fin
        )

        # Compteurs globaux
        kpi.nb_recommandations_creees = recommandations.count()
        kpi.nb_recommandations_terminees = recommandations.filter(statut='completed').count()
        kpi.nb_recommandations_en_retard = recommandations.filter(
            date_echeance__lt=timezone.now().date(),
            statut__in=['pending', 'approved', 'assigned', 'in_progress']
        ).count()

        # Répartition par type
        kpi.nb_correctifs = recommandations.filter(type_recommandation='correctif').count()
        kpi.nb_preventifs = recommandations.filter(type_recommandation='preventif').count()
        kpi.nb_ameliorations = recommandations.filter(type_recommandation='amelioration').count()
        kpi.nb_formations = recommandations.filter(type_recommandation='formation').count()

        # Répartition par priorité
        kpi.nb_critiques = recommandations.filter(priorite='critique').count()
        kpi.nb_hautes = recommandations.filter(priorite='haute').count()
        kpi.nb_moyennes = recommandations.filter(priorite='moyenne').count()
        kpi.nb_basses = recommandations.filter(priorite='basse').count()

        # Taux de completion
        if kpi.nb_recommandations_creees > 0:
            kpi.taux_completion = (kpi.nb_recommandations_terminees / kpi.nb_recommandations_creees) * 100

        return kpi

    def generer_rapport_mensuel(self, annee: int, mois: int) -> Dict[str, Any]:
        """Génère un rapport mensuel des KPIs"""

        from calendar import monthrange

        date_debut = date(annee, mois, 1)
        _, dernier_jour = monthrange(annee, mois)
        date_fin = date(annee, mois, dernier_jour)

        kpi = self.calculer_kpis_periode(date_debut, date_fin)

        return {
            'kpi': kpi,
            'periode': {
                'debut': date_debut,
                'fin': date_fin,
                'mois': mois,
                'annee': annee
            }
        }


class NotificationManager:
    """Gestionnaire de notifications pour les recommandations"""

    @staticmethod
    def notifier_nouvelle_recommandation(recommandation: Recommandation):
        """Notifie la création d'une nouvelle recommandation"""
        from .models import NotificationRecommandation

        # Notifier les administrateurs (globalement) et les utilisateurs de la mission concernée
        destinataires = User.objects.filter(
            Q(mission=recommandation.mission) | Q(role='admin')
        )

        for user in destinataires:
            NotificationRecommandation.objects.create(
                recommandation=recommandation,
                type_notification='nouvelle',
                destinataire=user,
                titre=f"Nouvelle recommandation : {recommandation.titre}",
                message=f"Une nouvelle recommandation a été créée pour la mission {recommandation.mission.name}."
            )

    @staticmethod
    def notifier_assignation(recommandation: Recommandation):
        """Notifie l'assignation d'une recommandation"""
        from .models import NotificationRecommandation

        if recommandation.assigne_a:
            NotificationRecommandation.objects.create(
                recommandation=recommandation,
                type_notification='assignation',
                destinataire=recommandation.assigne_a,
                titre=f"Recommandation assignée : {recommandation.code_recommandation}",
                message=f"La recommandation '{recommandation.titre}' vous a été assignée."
            )

    @staticmethod
    def notifier_echeance_proche(jours_avant=3):
        """Notifie les échéances proches"""
        from .models import NotificationRecommandation

        date_limite = timezone.now().date() + timedelta(days=jours_avant)

        recommandations_echeance = Recommandation.objects.filter(
            date_echeance__lte=date_limite,
            date_echeance__gte=timezone.now().date(),
            statut__in=['assigned', 'in_progress'],
            assigne_a__isnull=False
        )

        for reco in recommandations_echeance:
            # Éviter les doublons de notification
            if not NotificationRecommandation.objects.filter(
                    recommandation=reco,
                    type_notification='echeance_proche',
                    destinataire=reco.assigne_a,
                    date_creation__date=timezone.now().date()
            ).exists():
                jours_restants = (reco.date_echeance - timezone.now().date()).days

                NotificationRecommandation.objects.create(
                    recommandation=reco,
                    type_notification='echeance_proche',
                    destinataire=reco.assigne_a,
                    titre=f"Échéance proche : {reco.code_recommandation}",
                    message=f"La recommandation '{reco.titre}' arrive à échéance dans {jours_restants} jour(s)."
                )

    @staticmethod
    def notifier_retard():
        """Notifie les recommandations en retard"""
        from .models import NotificationRecommandation

        recommandations_retard = Recommandation.objects.filter(
            date_echeance__lt=timezone.now().date(),
            statut__in=['assigned', 'in_progress'],
            assigne_a__isnull=False
        )

        for reco in recommandations_retard:
            # Une notification par jour de retard max
            if not NotificationRecommandation.objects.filter(
                    recommandation=reco,
                    type_notification='retard',
                    destinataire=reco.assigne_a,
                    date_creation__date=timezone.now().date()
            ).exists():

                jours_retard = (timezone.now().date() - reco.date_echeance).days

                NotificationRecommandation.objects.create(
                    recommandation=reco,
                    type_notification='retard',
                    destinataire=reco.assigne_a,
                    titre=f"Retard : {reco.code_recommandation}",
                    message=f"La recommandation '{reco.titre}' est en retard de {jours_retard} jour(s)."
                )

                # Mettre à jour le statut si nécessaire
                if reco.statut != 'overdue':
                    reco.statut = 'overdue'
                    reco.save()
