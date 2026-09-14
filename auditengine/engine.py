# auditengine/engine.py
import uploads.dataprep
import sys
import contextlib
from uploads.dataprep import DataPrep
import os
import joblib
import pandas as pd
import numpy as np
import logging
from typing import Tuple, List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.db import transaction
import unicodedata
from difflib import SequenceMatcher

from .models import (
    SessionAudit, ResultatAudit, ParametrageIA, ModeleIA,
    CorrectionUtilisateur
)
from uploads.utils import FileProcessor

logger = logging.getLogger('auditia')


@contextlib.contextmanager
def _dataprep_comme_main():
    """Certains modèles .pkl ont été picklés alors que DataPrep vivait dans __main__
    (script exécuté directement). On le rend disponible sous ce nom uniquement le
    temps du chargement, au lieu de remplacer sys.modules['__main__'] pour tout le
    process — ce qui casserait multiprocessing/joblib (spawn), l'autoreloader Django,
    et tout autre unpickling qui attend le vrai __main__ ailleurs dans le process.
    """
    module_main_original = sys.modules.get('__main__')
    sys.modules['__main__'] = uploads.dataprep
    try:
        yield
    finally:
        if module_main_original is not None:
            sys.modules['__main__'] = module_main_original
        else:
            del sys.modules['__main__']


# ==================== FONCTIONS UTILITAIRES ====================

def get_recommandation_globale_type(type_anomalie: str, count: int) -> str:
    """Génère une recommandation globale pour un type d'anomalie"""

    recommandations = {
        'salaire_anormal': {
            1: "Contrôler ce salaire par rapport à la grille salariale",
            5: "Audit des grilles salariales recommandé",
            10: "Révision complète du système de rémunération nécessaire"
        },
        'ghost_employee': {
            1: "Vérification immédiate de l'existence de cet employé",
            2: "Audit des processus d'embauche et de présence",
            5: "Investigation approfondie pour fraude potentielle"
        },
        'prime_anormale': {
            1: "Contrôle de la justification de cette prime",
            5: "Révision des règles d'attribution des primes",
            10: "Audit complet du système de primes"
        },
        'heures_excessives': {
            1: "Vérification du respect du temps de travail",
            5: "Contrôle des heures supplémentaires et repos",
            10: "Audit de la planification et organisation du travail"
        },
        'duplicate_rib': {
            1: "Vérification de la légitimité du compte partagé",
            3: "Contrôle systématique des RIB",
            5: "Audit des procédures de gestion des comptes bancaires"
        }
    }

    type_reco = recommandations.get(type_anomalie, {})

    # Trouver la recommandation appropriée selon le nombre
    for seuil in sorted(type_reco.keys(), reverse=True):
        if count >= seuil:
            return type_reco[seuil]

    return "Contrôle de routine recommandé"


def generer_plan_action(analyse_types: Dict) -> List[Dict]:
    """Génère un plan d'action priorisé"""

    plan = []

    # Prioriser par ordre de risque
    ordre_priorite = ['ghost_employee', 'duplicate_rib', 'salaire_anormal', 'prime_anormale', 'heures_excessives']

    for type_anomalie in ordre_priorite:
        if type_anomalie in analyse_types:
            data = analyse_types[type_anomalie]

            if data['niveau_risque_max'] in ['critique', 'eleve']:
                delai = "Immédiat (24h)"
                responsable = "Direction + RH"
            elif data['count'] > 5:
                delai = "Court terme (1 semaine)"
                responsable = "Service RH"
            else:
                delai = "Moyen terme (1 mois)"
                responsable = "Gestionnaire de paie"

            plan.append({
                'type': data['label'],
                'action': data['recommandation_globale'],
                'delai': delai,
                'responsable': responsable,
                'count': data['count']
            })

    return plan


# Fonction utilitaire pour normaliser et mapper les colonnes DataFrame
COLONNES_VARIANTES = {
    'matricule': ['matricule', 'Matricule', 'MATRICULE'],
    'nom': ['nom', 'Nom', 'NOM', 'noms', 'Noms', 'NOMS'],
    'prenom': ['prenom', 'Prenom', 'PRENOM', 'prénom', 'Prénom', 'PRENOMS', 'Prénoms', 'prenoms'],
    'salaire_brut': ['salaire_brut', 'Salaire brut', 'salaire brut', 'SALAIRE BRUT', 'salairebrut', 'brut', 'Brut', 'salaire de base', 'Salaire de base', 'SALAIRE DE BASE', 'salaire_base', 'base', 'Base', 'BASE'],
    'montant_total': ['montant_total', 'montant total', 'salaire_net', 'salaire net', 'Salaire net', 'SALAIRE NET', 'salaire_net_a_payer', 'salaire net à payer', 'salaire net a payer', 'net', 'Net', 'montant_paye', 'montant payé', 'net à payer', 'Net à payer', 'NET À PAYER', 'net a payer', 'Net a payer', 'NET A PAYER'],
    'montant_primes': ['montant_primes', 'montant primes', 'Montant primes', 'primes', 'Primes', 'PRIMES', 'prime', 'Prime', 'PRIME'],
    'numero_compte': ['numero_compte', 'Numéro de compte', 'numero de compte', 'Numéro_compte', 'compte', 'Compte', 'compte bancaire', 'Compte bancaire', 'COMPTE BANCAIRE', 'banque', 'Banque', 'BANQUE'],
    'departement': ['departement', 'Département', 'Département/Service', 'departement/service', 'DEPARTEMENT', 'DEPARTEMENT/SERVICE'],
    'poste': ['poste', 'Poste', 'POSTE', 'poste/fonction', 'Poste/fonction', 'fonction', 'Fonction', 'FONCTION'],
    'statut': ['statut', 'Statut', 'STATUT', 'statut employé', 'Statut Employé', 'Statut Employé (CDD, CDI, EXPATRIE)'],
    'lieu_emploi': ['lieu emploi', 'Lieu Emploi', 'lieu_emploi', 'Lieu_Emploi', 'lieu', 'Lieu'],
    'date_embauche': ["Dates d'Embauche", 'date_embauche', 'Date embauche', 'embauche', 'Embauche'],
    'anciennete': ['anciennete', 'Ancienneté', 'ancienneté', 'Anciennete', 'Ancienneté (Nb années)', 'ancienneté (nb années)', 'Nb années', 'nb années'],
    'date_naissance': ['date_naissance', 'Date Naissance', 'date naissance', 'Naissance'],
    'age': ['age', 'Age', 'AGE', 'ages', 'Ages', 'AGES'],
    'classe_salariale': ['classe_salariale', 'Classe salariale', 'classe salariale', 'Classe Salariale'],
    'categorie_salariale': ['categorie_salariale', 'CATEGORIE salariale', 'Catégorie salariale', 'categorie salariale'],
    'heures_travaillees': ['heures_travaillees', 'Heures travaillées', 'heures travaillées', 'Heures Travaillées'],
    'primes': ['primes', 'Primes', 'PRIMES', 'primes ou avantages', 'Primes ou avantages', 'prime', 'Prime', 'PRIME'],
    'retenues': ['retenues', 'Retenues', 'RETENUES', 'retenues (impôts, assurances, autres)', 'Retenues (impôts, assurances, autres)', 'retenue', 'Retenue', 'RETENUE'],
    'date_paie': ['date_paie', 'Date de paie', 'date de paie', 'Date de paie (Chronologiquement)'],
    'annees_retraite': ['annees_retraite', 'Nombre Années Avant Retraite', 'nombre années avant retraite'],
    'salaire_net': ['salaire_net', 'salaire net', 'Salaire net', 'SALAIRE NET', 'net', 'Net', 'NET'],
}

def normaliser_nom_colonne(nom_colonne):
    if not nom_colonne:
        return ""
    nom_normalise = nom_colonne.lower().strip()
    nom_normalise = unicodedata.normalize('NFD', nom_normalise)
    nom_normalise = ''.join(c for c in nom_normalise if not unicodedata.combining(c))
    nom_normalise = nom_normalise.replace(' ', '_')
    return nom_normalise

def mapping_colonnes_robuste(df):
    """Renomme les colonnes du DataFrame selon les variantes connues"""
    mapping = {}
    colonnes_df = list(df.columns)
    for cible, variantes in COLONNES_VARIANTES.items():
        for variante in variantes:
            for col in colonnes_df:
                if normaliser_nom_colonne(col) == normaliser_nom_colonne(variante):
                    mapping[col] = cible
    return df.rename(columns=mapping)


# ==================== CLASSES PRINCIPALES ====================

class AuditEngine:
    """Moteur principal de détection d'anomalies par IA"""

    def __init__(self, session: SessionAudit):
        self.session = session
        self.config = ParametrageIA.get_config()
        self.logs = []

        # Modèles IA
        self.model_if = None
        self.model_mlp = None

        # Données de traitement
        self.df_data = None
        self.features_if = None
        self.features_mlp = None

    def executer_audit(self) -> bool:
        """Exécute l'audit complet avec les deux modèles"""
        import time
        start_time = time.time()

        try:
            self.session.status = 'processing'
            self.session.date_traitement = datetime.now()
            self.session.seuil_if_utilise = self.config.seuil_isolation_forest
            self.session.seuil_mlp_utilise = self.config.score_minimum_classification
            self.session.save()

            self._log("Début de l'audit IA")

            # 1. Charger et préparer les données
            self._charger_donnees()

            # 2. Charger les modèles IA
            self._charger_modeles()

            # 3. Préparer les features
            self._preparer_features()

            # 4. Exécuter Isolation Forest
            scores_if = self._executer_isolation_forest()

            # 5. Exécuter MLP Classifier sur les anomalies
            predictions_mlp = self._executer_mlp_classifier(scores_if)

            # 6. Générer les recommandations
            recommandations = self._generer_recommandations(predictions_mlp)

            # 7. Sauvegarder les résultats
            self._sauvegarder_resultats(scores_if, predictions_mlp, recommandations)

            # 8. Calculer les statistiques
            self._calculer_statistiques()

            # Finalisation
            end_time = time.time()
            self.session.duree_traitement_secondes = round(end_time - start_time, 2)
            self.session.status = 'completed'
            self.session.date_completion = datetime.now()
            self.session.logs_traitement = self.logs
            self.session.save()

            self._log(f"Audit terminé en {self.session.duree_traitement_secondes} secondes")
            return True

        except Exception as e:
            self.session.status = 'error'
            self.session.erreurs = str(e)
            self.session.logs_traitement = self.logs
            self.session.save()
            logger.error(f"Erreur audit session {self.session.id}: {str(e)}")
            return False

    def _charger_donnees(self):
        """Charge et nettoie les données du fichier de paie"""
        self._log("Chargement des données...")

        # Charger le fichier de paie
        self.df_data = FileProcessor.lire_fichier(self.session.fichier_paie)
        self._log(f"Fichier chargé: {len(self.df_data)} lignes")

        # Appliquer le mapping robuste juste après le chargement des données :
        self.df_data = mapping_colonnes_robuste(self.df_data)

        # Normaliser les colonnes
        self.df_data.columns = self.df_data.columns.str.lower().str.strip()

        # Nettoyer les données
        self._nettoyer_donnees()

        # Ajouter index pour traçabilité
        self.df_data['ligne_origine'] = self.df_data.index + 1

        self.session.nb_lignes_analysees = len(self.df_data)
        self.session.save()

    def _nettoyer_donnees(self):
        """Nettoie et normalise les données"""
        # Normaliser les noms/prénoms
        for col in ['nom', 'prenom']:
            if col in self.df_data.columns:
                self.df_data[col] = self.df_data[col].astype(str).str.strip().str.title()

        # Nettoyer les matricules
        if 'matricule' in self.df_data.columns:
            self.df_data['matricule'] = self.df_data['matricule'].astype(str).str.strip()

        # Convertir les montants
        for col in ['salaire_brut', 'montant_total', 'montant_primes']:
            if col in self.df_data.columns:
                self.df_data[col] = pd.to_numeric(self.df_data[col], errors='coerce').fillna(0)

        # Convertir les heures
        if 'heures_travaillees' in self.df_data.columns:
            self.df_data['heures_travaillees'] = pd.to_numeric(
                self.df_data['heures_travaillees'], errors='coerce'
            ).fillna(0)

        # Nettoyer les RIB
        if 'rib' in self.df_data.columns:
            self.df_data['rib'] = self.df_data['rib'].astype(str).str.strip()

    def _charger_modeles(self):
        """Charge les modèles IA depuis les fichiers .pkl"""
        self._log("Chargement des modèles IA...")

        try:
            with _dataprep_comme_main():
                # Modèle Isolation Forest
                model_if_obj = ModeleIA.get_modele_actif('isolation_forest', self.session.mission)
                if model_if_obj:
                    self.model_if = joblib.load(model_if_obj.get_chemin_complet())
                    self.session.modele_utilise = f"IF: {model_if_obj.nom_modele}"
                    self._log(f"Modèle IF chargé: {model_if_obj.nom_modele}")
                else:
                    # Fallback sur le modèle par défaut
                    chemin_if = os.path.join(settings.BASE_DIR, 'ml_models', 'model_iforest.pkl')
                    self.model_if = joblib.load(chemin_if)
                    self.session.modele_utilise = "IF: model_iforest.pkl (défaut)"
                    self._log("Modèle IF par défaut chargé")

                # Modèle MLP Classifier
                model_mlp_obj = ModeleIA.get_modele_actif('mlp_classifier', self.session.mission)
                if model_mlp_obj:
                    self.model_mlp = joblib.load(model_mlp_obj.get_chemin_complet())
                    self.session.modele_utilise += f" | MLP: {model_mlp_obj.nom_modele}"
                    self._log(f"Modèle MLP chargé: {model_mlp_obj.nom_modele}")
                else:
                    # Fallback sur le modèle par défaut
                    chemin_mlp = os.path.join(settings.BASE_DIR, 'ml_models', 'model_mlp.pkl')
                    self.model_mlp = joblib.load(chemin_mlp)
                    self.session.modele_utilise += " | MLP: model_mlp.pkl (défaut)"
                    self._log("Modèle MLP par défaut chargé")

            self.session.save()

        except Exception as e:
            raise Exception(f"Erreur chargement modèles: {str(e)}")

    def _preparer_features(self):
        """Prépare les features pour les modèles"""
        self._log("Préparation des features...")

        # Features pour Isolation Forest (détection d'anomalies)
        self.features_if = self._extraire_features_isolation_forest()

        # Features pour MLP (classification)
        self.features_mlp = self._extraire_features_mlp()

        self._log(f"Features IF: {self.features_if.shape}, Features MLP: {self.features_mlp.shape}")

    def _extraire_features_isolation_forest(self) -> pd.DataFrame:
        """Extrait les features numériques pour Isolation Forest"""
        features = pd.DataFrame()

        # Récupérer la liste des features attendues par le modèle (ordre et noms)
        feature_names = None
        if self.model_if is not None and hasattr(self.model_if, 'feature_names_in_'):
            feature_names = list(self.model_if.feature_names_in_)
        else:
            # fallback: liste standard
            feature_names = [
                'age', 'anciennete', 'salaire_brut', 'heures_travaillees',
                'primes', 'retenues', 'salaire_net', 'annees_retraite',
                'montant_total', 'montant_primes'
            ]

        # Pour chaque feature attendue, prendre la colonne ou mettre 0 si absente
        for col in feature_names:
            if col in self.df_data.columns:
                features[col] = self.df_data[col]
            else:
                features[col] = 0

        # Remplacer les valeurs infinies et NaN
        features = features.replace([np.inf, -np.inf], 0).fillna(0)
        return features

    def _extraire_features_mlp(self) -> pd.DataFrame:
        """Extrait les features pour le classificateur MLP"""
        # On part de features_if mais on doit matcher exactement les features attendues par le modèle MLP
        features = self.features_if.copy()

        # Récupérer la liste des features attendues par le modèle MLP
        feature_names = None
        if self.model_mlp is not None and hasattr(self.model_mlp, 'feature_names_in_'):
            feature_names = list(self.model_mlp.feature_names_in_)
        else:
            # fallback: liste standard (à adapter si besoin)
            feature_names = list(features.columns)

        # Pour chaque feature attendue, prendre la colonne ou mettre 0 si absente
        features_final = pd.DataFrame()
        for col in feature_names:
            if col in features.columns:
                features_final[col] = features[col]
            else:
                features_final[col] = 0

        # Remplacer les valeurs infinies et NaN
        features_final = features_final.replace([np.inf, -np.inf], 0).fillna(0)
        return features_final

    def _executer_isolation_forest(self) -> List[Dict]:
        """Exécute la détection d'anomalies avec Isolation Forest"""
        self._log("Exécution Isolation Forest...")

        try:
            # Prédiction des anomalies (-1 = anomalie, 1 = normal)
            predictions = self.model_if.predict(self.features_if)

            # Scores d'anomalie (plus proche de 0 = plus anormal)
            scores = self.model_if.decision_function(self.features_if)

            # Normaliser les scores (0-1, plus proche de 1 = plus anormal)
            scores_normalized = 1 - ((scores - scores.min()) / (scores.max() - scores.min() + 1e-8))

            resultats = []
            for i, (prediction, score) in enumerate(zip(predictions, scores_normalized)):
                # CORRECTION: Seulement utiliser la prédiction du modèle, pas le seuil
                # Le seuil sera utilisé plus tard dans la logique combinée
                est_anomalie = (prediction == -1)

                # Explication simple
                explication = self._generer_explication_if(i, score, est_anomalie)

                resultats.append({
                    'index': i,
                    'est_anomalie': est_anomalie,
                    'score_anomalie': float(score),
                    'explication': explication
                })

            nb_anomalies = sum(1 for r in resultats if r['est_anomalie'])
            self._log(f"IF: {nb_anomalies} anomalies détectées sur {len(resultats)} lignes")

            return resultats

        except Exception as e:
            raise Exception(f"Erreur Isolation Forest: {str(e)}")

    def _executer_mlp_classifier(self, scores_if: List[Dict]) -> List[Dict]:
        """Exécute la classification MLP sur les anomalies détectées"""
        self._log("Exécution MLP Classifier...")

        try:
            # Prédictions pour toutes les lignes
            predictions = self.model_mlp.predict(self.features_mlp)
            probabilities = self.model_mlp.predict_proba(self.features_mlp)

            # Classes possibles du modèle
            classes = self.model_mlp.classes_

            resultats = []
            for i, (pred, proba_array, score_if_data) in enumerate(zip(predictions, probabilities, scores_if)):
                # Score de confiance = probabilité max
                max_proba = float(np.max(proba_array))

                # Type d'anomalie prédit
                type_anomalie = str(pred)

                # CORRECTION: Logique améliorée pour la détection d'anomalies
                # 1. Si Isolation Forest détecte une anomalie ET MLP est confiant
                if (score_if_data['est_anomalie'] and 
                    max_proba >= self.config.score_minimum_classification):
                    # Garder le type d'anomalie prédit par MLP
                    pass
                # 2. Si Isolation Forest détecte une anomalie mais MLP pas très confiant
                elif score_if_data['est_anomalie'] and max_proba < self.config.score_minimum_classification:
                    # Anomalie détectée mais type incertain - utiliser le type prédit même si pas très confiant
                    # mais seulement si le score est raisonnable (> 0.3)
                    if max_proba > 0.3:
                        # Garder le type prédit mais avec un score plus faible
                        pass
                    else:
                        # Pas assez confiant, utiliser une classification basée sur les données
                        # Analyser les features pour déterminer le type le plus probable
                        row = self.features_mlp.iloc[i]
                        if 'salaire_brut' in row and row['salaire_brut'] > 5000:
                            type_anomalie = 'salaire_anormal'
                        elif not row.get('nom', '') or not row.get('prenom', ''):
                            type_anomalie = 'ghost_employee'
                        elif row.get('montant_primes', 0) > 1000:
                            type_anomalie = 'prime_anormale'
                        elif row.get('heures_travaillees', 0) > 200:
                            type_anomalie = 'heures_excessives'
                        else:
                            type_anomalie = 'salaire_anormal'  # Par défaut
                        max_proba = score_if_data['score_anomalie']
                # 3. Si Isolation Forest ne détecte pas d'anomalie
                else:
                    # Pas d'anomalie détectée
                    type_anomalie = 'aucune'
                    max_proba = 0.0

                # Niveau de risque basé sur le score combiné
                niveau_risque = self._calculer_niveau_risque(
                    score_if_data['score_anomalie'],
                    max_proba
                )

                # Explication
                explication = self._generer_explication_mlp(i, type_anomalie, max_proba)

                resultats.append({
                    'index': i,
                    'type_anomalie': type_anomalie,
                    'score_classification': max_proba,
                    'niveau_risque': niveau_risque,
                    'explication': explication,
                    'probabilities': {cls: float(prob) for cls, prob in zip(classes, proba_array)}
                })

            # Statistiques
            types_detectes = {}
            for r in resultats:
                type_anom = r['type_anomalie']
                types_detectes[type_anom] = types_detectes.get(type_anom, 0) + 1

            self._log(f"MLP: Types détectés - {types_detectes}")

            return resultats

        except Exception as e:
            raise Exception(f"Erreur MLP Classifier: {str(e)}")

    def _calculer_niveau_risque(self, score_if: float, score_mlp: float) -> str:
        """Calcule le niveau de risque combiné"""
        score_combine = (score_if + score_mlp) / 2

        if score_combine >= 0.9:
            return 'critique'
        elif score_combine >= 0.75:
            return 'eleve'
        elif score_combine >= 0.5:
            return 'moyen'
        else:
            return 'faible'

    def _generer_explication_if(self, index: int, score: float, est_anomalie: bool) -> str:
        """Génère une explication pour la détection Isolation Forest"""
        if not est_anomalie:
            return f"Profil normal (score: {score:.3f})"

        # Analyser quelles features contribuent le plus à l'anomalie
        row = self.features_if.iloc[index]
        explications = []

        # Vérifier les valeurs extrêmes
        if 'salaire_brut' in row and row['salaire_brut'] > self.features_if['salaire_brut'].quantile(0.95):
            explications.append("salaire très élevé")
        elif 'salaire_brut' in row and row['salaire_brut'] < self.features_if['salaire_brut'].quantile(0.05):
            explications.append("salaire très faible")

        if 'heures_travaillees' in row and row['heures_travaillees'] > 60:
            explications.append("heures excessives")

        if 'ratio_primes_salaire' in row and row['ratio_primes_salaire'] > 0.5:
            explications.append("ratio primes/salaire élevé")

        if explications:
            return f"Anomalie détectée (score: {score:.3f}) - {', '.join(explications)}"
        else:
            return f"Anomalie détectée (score: {score:.3f}) - profil atypique"

    def _generer_explication_mlp(self, index: int, type_anomalie: str, score: float) -> str:
        """Génère une explication pour la classification MLP"""
        if type_anomalie == 'aucune':
            return "Aucune anomalie spécifique identifiée"

        explications = {
            'salaire_anormal': f"Salaire anormal détecté (confiance: {score:.1%})",
            'ghost_employee': f"Possible employé fantôme (confiance: {score:.1%})",
            'prime_anormale': f"Prime anormale détectée (confiance: {score:.1%})",
            'heures_excessives': f"Heures de travail excessives (confiance: {score:.1%})",
            'duplicate_rib': f"RIB dupliqué détecté (confiance: {score:.1%})"
        }

        return explications.get(type_anomalie, f"Anomalie {type_anomalie} (confiance: {score:.1%})")

    def _generer_recommandations(self, predictions_mlp: List[Dict]) -> List[str]:
        """Génère des recommandations automatiques basées sur les types d'anomalies"""
        self._log("Génération des recommandations...")

        recommandations = []
        for pred in predictions_mlp:
            type_anomalie = pred['type_anomalie']
            niveau_risque = pred['niveau_risque']

            recommandation = self._get_recommandation_par_type(type_anomalie, niveau_risque)
            recommandations.append(recommandation)

        return recommandations

    def _get_recommandation_par_type(self, type_anomalie: str, niveau_risque: str) -> str:
        """Retourne la recommandation spécifique pour un type d'anomalie"""
        recommandations_base = {
            'salaire_anormal': {
                'critique': "🚨 URGENT: Vérifier immédiatement ce salaire avec les RH et la grille salariale",
                'eleve': "⚠️ Contrôler ce salaire par rapport à la grille et au poste occupé",
                'moyen': "📋 Vérifier la cohérence avec la convention collective",
                'faible': "📝 Salaire légèrement atypique, contrôle de routine recommandé"
            },
            'ghost_employee': {
                'critique': "🚨 URGENT: Possible fraude - employé fantôme détecté, enquête immédiate",
                'eleve': "⚠️ Vérifier l'existence réelle de cet employé dans les services",
                'moyen': "📋 Contrôler la présence physique et les justificatifs d'embauche",
                'faible': "📝 Vérifier les informations de base de cet employé"
            },
            'prime_anormale': {
                'critique': "🚨 URGENT: Prime exceptionnellement élevée, vérifier l'autorisation",
                'eleve': "⚠️ Contrôler la justification et l'autorisation de cette prime",
                'moyen': "📋 Vérifier la conformité avec les règles de primes",
                'faible': "📝 Prime légèrement atypique, contrôle de routine"
            },
            'heures_excessives': {
                'critique': "🚨 URGENT: Heures dangereusement élevées, risque légal et santé",
                'eleve': "⚠️ Contrôler le respect du temps de travail et des repos",
                'moyen': "📋 Vérifier la justification des heures supplémentaires",
                'faible': "📝 Heures légèrement élevées, surveillance recommandée"
            },
            'duplicate_rib': {
                'critique': "🚨 URGENT: RIB dupliqué détecté, risque de fraude ou erreur grave",
                'eleve': "⚠️ Vérifier immédiatement l'unicité des comptes bancaires",
                'moyen': "📋 Contrôler les RIB et demander justification si partagé",
                'faible': "📝 RIB partagé détecté, vérifier si légitime (famille)"
            },
            'aucune': "✅ Aucune anomalie détectée, profil normal"
        }

        val = recommandations_base.get(type_anomalie, {})
        if isinstance(val, dict):
            return val.get(niveau_risque, "📝 Anomalie détectée, contrôle recommandé")
        return val  # C'est déjà une chaîne

    def _sauvegarder_resultats(self, scores_if: List[Dict], predictions_mlp: List[Dict],
                               recommandations: List[str]):
        """Sauvegarde tous les résultats en base de données"""
        self._log("Sauvegarde des résultats...")

        # Supprimer les anciens résultats
        ResultatAudit.objects.filter(session=self.session).delete()

        # Créer les nouveaux résultats
        resultats_a_creer = []
        for i, (score_if, pred_mlp, recommandation) in enumerate(
                zip(scores_if, predictions_mlp, recommandations)
        ):
            row = self.df_data.iloc[i]

            # CORRECTION: Logique améliorée pour déterminer si c'est une anomalie
            # Une anomalie est détectée si :
            # 1. Isolation Forest détecte une anomalie ET
            # 2. Le type n'est pas 'aucune'
            est_anomalie_finale = (score_if['est_anomalie'] and 
                                 pred_mlp['type_anomalie'] != 'aucune')

            # Correction de la logique de recommandation
            if score_if['est_anomalie'] and pred_mlp['type_anomalie'] == 'aucune':
                recommandation_finale = "⚠️ Anomalie détectée par l'IA, vérification manuelle recommandée"
            elif pred_mlp['type_anomalie'] == 'anomalie_non_classifiee':
                recommandation_finale = "🔍 Anomalie détectée mais type incertain - Vérification manuelle requise"
            else:
                recommandation_finale = self._get_recommandation_par_type(pred_mlp['type_anomalie'], pred_mlp['niveau_risque'])

            resultat = ResultatAudit(
                session=self.session,
                ligne_fichier=row.get('ligne_origine', i + 1),
                matricule=str(row.get('matricule', '')),
                nom=str(row.get('nom', '')),
                prenom=str(row.get('prenom', '')),
                poste=str(row.get('poste', '')),
                rib=str(row.get('rib', '')),
                salaire_brut=self._to_decimal(row.get('salaire_brut')),
                montant_total=self._to_decimal(row.get('montant_total')),
                heures_travaillees=row.get('heures_travaillees'),
                montant_primes=self._to_decimal(row.get('montant_primes')),
                est_anomalie=est_anomalie_finale,
                score_anomalie_if=score_if['score_anomalie'],
                type_anomalie=pred_mlp['type_anomalie'],
                score_classification_mlp=pred_mlp['score_classification'],
                niveau_risque=pred_mlp['niveau_risque'],
                explication_if=score_if['explication'],
                explication_mlp=pred_mlp['explication'],
                recommandation_auto=recommandation_finale
            )
            resultats_a_creer.append(resultat)

        # Bulk create pour la performance
        ResultatAudit.objects.bulk_create(resultats_a_creer, batch_size=100)

        self._log(f"Sauvegardé {len(resultats_a_creer)} résultats")

    def _calculer_statistiques(self):
        """Calcule et sauvegarde les statistiques globales"""
        resultats = ResultatAudit.objects.filter(session=self.session)

        self.session.nb_anomalies_detectees = resultats.filter(est_anomalie=True).count()
        self.session.nb_salaires_anormaux = resultats.filter(type_anomalie='salaire_anormal').count()
        self.session.nb_employes_fantomes = resultats.filter(type_anomalie='ghost_employee').count()
        self.session.nb_primes_anormales = resultats.filter(type_anomalie='prime_anormale').count()
        self.session.nb_heures_excessives = resultats.filter(type_anomalie='heures_excessives').count()
        self.session.nb_rib_dupliques = resultats.filter(type_anomalie='duplicate_rib').count()
        self.session.nb_aucune_anomalie = resultats.filter(type_anomalie='aucune').count()

        self._log(f"Statistiques: {self.session.get_taux_anomalies()}% d'anomalies détectées")

    def _to_decimal(self, valeur) -> Optional[Decimal]:
        """Convertit une valeur en Decimal pour stockage"""
        try:
            if pd.isna(valeur) or valeur == '':
                return None
            return Decimal(str(float(valeur)))
        except (ValueError, TypeError):
            return None

    def _log(self, message: str):
        """Ajoute un message aux logs"""
        self.logs.append({
            'timestamp': datetime.now().isoformat(),
            'message': message
        })
        logger.info(f"AuditEngine [{self.session.id}]: {message}")

    class RetrainingEngine:
        """Moteur de réentraînement des modèles avec les corrections utilisateur"""

        def __init__(self, mission=None, utilisateur=None):
            self.mission = mission
            self.utilisateur = utilisateur
            self.logs = []

        def reentrainer_modeles(self, type_modele: str = 'both') -> bool:
            """Réentraîne les modèles avec les corrections utilisateur"""
            try:
                self._log(f"Début du réentraînement - Type: {type_modele}")

                # Récupérer les corrections non utilisées
                corrections = self._get_corrections_pour_entrainement()

                if len(corrections) < 10:  # Minimum de corrections requis
                    self._log(f"Pas assez de corrections ({len(corrections)}), réentraînement annulé")
                    return False

                # Préparer les données d'entraînement
                X_train, y_train = self._preparer_donnees_entrainement(corrections)

                if type_modele in ['isolation_forest', 'both']:
                    self._reentrainer_isolation_forest(X_train)

                if type_modele in ['mlp_classifier', 'both']:
                    self._reentrainer_mlp_classifier(X_train, y_train)

                # Marquer les corrections comme utilisées
                self._marquer_corrections_utilisees(corrections)

                self._log("Réentraînement terminé avec succès")
                return True

            except Exception as e:
                self._log(f"Erreur lors du réentraînement: {str(e)}")
                logger.error(f"Erreur réentraînement: {str(e)}")
                return False

        def _get_createur_id(self):
            """ID à associer au modèle réentraîné : l'utilisateur ayant déclenché le
            réentraînement, ou à défaut le premier superutilisateur (au lieu de supposer
            que l'utilisateur d'ID 1 existe toujours)."""
            if self.utilisateur:
                return self.utilisateur.id
            from django.contrib.auth import get_user_model
            fallback = get_user_model().objects.filter(is_superuser=True).order_by('id').first()
            return fallback.id if fallback else None

        def _get_corrections_pour_entrainement(self):
            """Récupère les corrections utilisateur non encore utilisées"""
            corrections = CorrectionUtilisateur.objects.filter(
                utilisee_pour_entrainement=False,
                confiance_utilisateur__gte=7  # Minimum de confiance
            )

            if self.mission:
                corrections = corrections.filter(
                    resultat_audit__session__mission=self.mission
                )

            return corrections

        def _preparer_donnees_entrainement(self, corrections):
            """Prépare les données pour le réentraînement"""
            # Cette méthode devrait extraire les features des résultats corrigés
            # et créer des datasets d'entraînement appropriés
            # Implémentation simplifiée pour l'exemple

            X_train = []
            y_train = []

            for correction in corrections:
                resultat = correction.resultat_audit
                # Extraire les features du résultat original
                # et utiliser la correction comme label
                pass

            return np.array(X_train), np.array(y_train)

        def _reentrainer_isolation_forest(self, X_train):
            """Réentraîne le modèle Isolation Forest"""
            self._log("Réentraînement Isolation Forest...")

            try:
                from sklearn.ensemble import IsolationForest

                # Créer et entraîner le nouveau modèle
                nouveau_modele = IsolationForest(
                    contamination=0.1,  # 10% d'anomalies attendues
                    random_state=42,
                    n_estimators=100
                )

                nouveau_modele.fit(X_train)

                # Sauvegarder le nouveau modèle
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nom_fichier = f"retrained_iforest_{timestamp}.pkl"

                if self.mission:
                    nom_fichier = f"mission_{self.mission.id}_{nom_fichier}"

                chemin_complet = os.path.join(settings.BASE_DIR, 'ml_models', nom_fichier)
                joblib.dump(nouveau_modele, chemin_complet)

                # Créer l'enregistrement en base
                ModeleIA.objects.create(
                    nom_modele=f"IF Retrained {timestamp}",
                    type_modele='isolation_forest',
                    scope='mission' if self.mission else 'global',
                    mission=self.mission,
                    fichier_modele=nom_fichier,
                    version=f"retrained_{timestamp}",
                    description=f"Modèle réentraîné avec {len(X_train)} corrections utilisateur",
                    date_entrainement=datetime.now(),
                    est_actif=True,
                    cree_par_id=self._get_createur_id()
                )

                # Désactiver l'ancien modèle
                anciens_modeles = ModeleIA.objects.filter(
                    type_modele='isolation_forest',
                    scope='mission' if self.mission else 'global',
                    mission=self.mission,
                    est_actif=True
                ).exclude(fichier_modele=nom_fichier)

                anciens_modeles.update(est_actif=False)

                self._log(f"Modèle IF sauvegardé: {nom_fichier}")

            except Exception as e:
                raise Exception(f"Erreur réentraînement IF: {str(e)}")

        def _reentrainer_mlp_classifier(self, X_train, y_train):
            """Réentraîne le modèle MLP Classifier"""
            self._log("Réentraînement MLP Classifier...")

            try:
                from sklearn.neural_network import MLPClassifier
                from sklearn.preprocessing import StandardScaler
                from sklearn.pipeline import Pipeline
                from sklearn.model_selection import train_test_split
                from sklearn.metrics import classification_report

                # Créer le pipeline avec normalisation
                pipeline = Pipeline([
                    ('scaler', StandardScaler()),
                    ('mlp', MLPClassifier(
                        hidden_layer_sizes=(100, 50),
                        max_iter=1000,
                        random_state=42,
                        early_stopping=True,
                        validation_fraction=0.2
                    ))
                ])

                # Entraîner le modèle
                if len(np.unique(y_train)) > 1:  # Vérifier qu'il y a plusieurs classes
                    pipeline.fit(X_train, y_train)

                    # Évaluation rapide
                    if len(X_train) > 20:  # Split seulement si assez de données
                        X_train_split, X_test_split, y_train_split, y_test_split = train_test_split(
                            X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
                        )
                        pipeline.fit(X_train_split, y_train_split)
                        score = pipeline.score(X_test_split, y_test_split)
                        self._log(f"Score de validation: {score:.3f}")

                    # Sauvegarder le nouveau modèle
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    nom_fichier = f"retrained_mlp_{timestamp}.pkl"

                    if self.mission:
                        nom_fichier = f"mission_{self.mission.id}_{nom_fichier}"

                    chemin_complet = os.path.join(settings.BASE_DIR, 'ml_models', nom_fichier)
                    joblib.dump(pipeline, chemin_complet)

                    # Créer l'enregistrement en base
                    ModeleIA.objects.create(
                        nom_modele=f"MLP Retrained {timestamp}",
                        type_modele='mlp_classifier',
                        scope='mission' if self.mission else 'global',
                        mission=self.mission,
                        fichier_modele=nom_fichier,
                        version=f"retrained_{timestamp}",
                        description=f"Modèle réentraîné avec {len(X_train)} corrections utilisateur",
                        accuracy=score if 'score' in locals() else None,
                        date_entrainement=datetime.now(),
                        est_actif=True,
                        cree_par_id=self._get_createur_id()
                    )

                    # Désactiver l'ancien modèle
                    anciens_modeles = ModeleIA.objects.filter(
                        type_modele='mlp_classifier',
                        scope='mission' if self.mission else 'global',
                        mission=self.mission,
                        est_actif=True
                    ).exclude(fichier_modele=nom_fichier)

                    anciens_modeles.update(est_actif=False)

                    self._log(f"Modèle MLP sauvegardé: {nom_fichier}")
                else:
                    self._log("Pas assez de classes différentes pour réentraîner MLP")

            except Exception as e:
                raise Exception(f"Erreur réentraînement MLP: {str(e)}")

        def _marquer_corrections_utilisees(self, corrections):
            """Marque les corrections comme utilisées pour l'entraînement"""
            corrections.update(utilisee_pour_entrainement=True)
            self._log(f"Marqué {len(corrections)} corrections comme utilisées")

        def _log(self, message: str):
            """Ajoute un message aux logs"""
            self.logs.append({
                'timestamp': datetime.now().isoformat(),
                'message': message
            })
            logger.info(f"RetrainingEngine: {message}")

    class ModelEvaluator:
        """Évaluateur de performance des modèles"""

        def __init__(self):
            self.logs = []

        def evaluer_modele(self, modele_id: int) -> Dict[str, Any]:
            """Évalue les performances d'un modèle spécifique"""
            try:
                modele = ModeleIA.objects.get(id=modele_id)
                self._log(f"Évaluation du modèle: {modele.nom_modele}")

                # Charger le modèle
                with _dataprep_comme_main():
                    model = joblib.load(modele.get_chemin_complet())

                # Récupérer les données de test (dernières sessions auditées)
                sessions_test = self._get_sessions_test(modele.mission)

                if not sessions_test:
                    return {'error': 'Pas de données de test disponibles'}

                # Évaluer selon le type de modèle
                if modele.type_modele == 'isolation_forest':
                    metriques = self._evaluer_isolation_forest(model, sessions_test)
                elif modele.type_modele == 'mlp_classifier':
                    metriques = self._evaluer_mlp_classifier(model, sessions_test)
                else:
                    return {'error': 'Type de modèle non supporté'}

                # Mettre à jour les métriques en base
                self._mettre_a_jour_metriques(modele, metriques)

                return metriques

            except Exception as e:
                self._log(f"Erreur évaluation: {str(e)}")
                return {'error': str(e)}

        def _get_sessions_test(self, mission=None):
            """Récupère les sessions pour les tests"""
            sessions = SessionAudit.objects.filter(status='completed')

            if mission:
                sessions = sessions.filter(mission=mission)

            # Prendre les 10 dernières sessions pour le test
            return sessions.order_by('-date_completion')[:10]

        def _evaluer_isolation_forest(self, model, sessions_test) -> Dict[str, Any]:
            """Évalue un modèle Isolation Forest"""
            total_predictions = 0
            correct_predictions = 0
            false_positives = 0
            false_negatives = 0

            for session in sessions_test:
                # Récupérer les résultats validés par les utilisateurs
                resultats_valides = session.resultats.filter(valide_par_humain=True)

                for resultat in resultats_valides:
                    total_predictions += 1

                    # Vérité terrain (après correction utilisateur)
                    vraie_anomalie = resultat.est_anomalie and not resultat.est_fausse_alerte

                    # Prédiction du modèle
                    prediction_anomalie = resultat.score_anomalie_if >= 0.75  # Seuil par défaut

                    if vraie_anomalie == prediction_anomalie:
                        correct_predictions += 1
                    elif prediction_anomalie and not vraie_anomalie:
                        false_positives += 1
                    elif not prediction_anomalie and vraie_anomalie:
                        false_negatives += 1

            if total_predictions == 0:
                return {'error': 'Pas de données validées pour l\'évaluation'}

            accuracy = correct_predictions / total_predictions
            precision = correct_predictions / (correct_predictions + false_positives) if (
                                                                                                     correct_predictions + false_positives) > 0 else 0
            recall = correct_predictions / (correct_predictions + false_negatives) if (
                                                                                                  correct_predictions + false_negatives) > 0 else 0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

            return {
                'accuracy': round(accuracy, 4),
                'precision': round(precision, 4),
                'recall': round(recall, 4),
                'f1_score': round(f1_score, 4),
                'total_predictions': total_predictions,
                'false_positives': false_positives,
                'false_negatives': false_negatives
            }

        def _evaluer_mlp_classifier(self, model, sessions_test) -> Dict[str, Any]:
            """Évalue un modèle MLP Classifier"""
            y_true = []
            y_pred = []

            for session in sessions_test:
                resultats_valides = session.resultats.filter(valide_par_humain=True)

                for resultat in resultats_valides:
                    # Vérité terrain (après correction)
                    vrai_type = resultat.type_anomalie
                    if resultat.est_fausse_alerte:
                        vrai_type = 'aucune'

                    # Prédiction du modèle
                    pred_type = resultat.type_anomalie

                    y_true.append(vrai_type)
                    y_pred.append(pred_type)

            if len(y_true) == 0:
                return {'error': 'Pas de données validées pour l\'évaluation'}

            # Calculer les métriques
            try:
                from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, \
                    classification_report

                accuracy = accuracy_score(y_true, y_pred)
                precision = precision_score(y_true, y_pred, average='weighted', zero_division=0)
                recall = recall_score(y_true, y_pred, average='weighted', zero_division=0)
                f1 = f1_score(y_true, y_pred, average='weighted', zero_division=0)

                # Rapport détaillé
                rapport_classes = classification_report(y_true, y_pred, output_dict=True, zero_division=0)

                return {
                    'accuracy': round(accuracy, 4),
                    'precision': round(precision, 4),
                    'recall': round(recall, 4),
                    'f1_score': round(f1, 4),
                    'total_predictions': len(y_true),
                    'classes_report': rapport_classes
                }

            except Exception as e:
                return {'error': f'Erreur calcul métriques: {str(e)}'}

        def _mettre_a_jour_metriques(self, modele: ModeleIA, metriques: Dict[str, Any]):
            """Met à jour les métriques du modèle en base"""
            if 'error' not in metriques:
                modele.accuracy = metriques.get('accuracy')
                modele.precision = metriques.get('precision')
                modele.recall = metriques.get('recall')
                modele.f1_score = metriques.get('f1_score')
                modele.save()

                self._log(f"Métriques mises à jour pour {modele.nom_modele}")

        def _log(self, message: str):
            """Ajoute un message aux logs"""
            self.logs.append({
                'timestamp': datetime.now().isoformat(),
                'message': message
            })
            logger.info(f"ModelEvaluator: {message}")

    class RecommendationGenerator:
        """Générateur de recommandations basées sur les anomalies détectées"""

        @staticmethod
        def generer_recommandations_session(session: SessionAudit) -> Dict[str, Any]:
            """Génère un rapport de recommandations pour une session complète"""

            resultats = session.resultats.all()
            anomalies = resultats.filter(est_anomalie=True)

            # Analyse par type d'anomalie
            analyse_types = {}
            for type_code, type_label in ResultatAudit.TYPE_ANOMALIE_CHOICES:
                if type_code == 'aucune':
                    continue

                anomalies_type = anomalies.filter(type_anomalie=type_code)
                if anomalies_type.exists():
                    count = anomalies_type.count()
                    analyse_types[type_code] = {
                        'label': type_label,
                        'count': count,
                        'niveau_risque_max': anomalies_type.order_by('-niveau_risque').first().niveau_risque,
                        'recommandation_globale': get_recommandation_globale_type(type_code, count),
                        'exemples': list(anomalies_type.order_by('-score_anomalie_if')[:3].values(
                            'nom', 'prenom', 'salaire_brut', 'niveau_risque'
                        ))
                    }

            # Recommandations prioritaires
            recommandations_prioritaires = []

            # Risques critiques
            critiques = anomalies.filter(niveau_risque='critique')
            if critiques.exists():
                recommandations_prioritaires.append({
                    'priorite': 'URGENT',
                    'titre': f"{critiques.count()} anomalie(s) critique(s) détectée(s)",
                    'action': "Intervention immédiate requise",
                    'details': "Ces anomalies présentent un risque élevé de fraude ou d'erreur grave"
                })

            # Employés fantômes
            fantomes = anomalies.filter(type_anomalie='ghost_employee')
            if fantomes.exists():
                recommandations_prioritaires.append({
                    'priorite': 'URGENT',
                    'titre': f"{fantomes.count()} employé(s) fantôme(s) potentiel(s)",
                    'action': "Vérification d'existence immédiate",
                    'details': "Risque de fraude interne élevé"
                })

            # RIB dupliqués
            rib_dupes = anomalies.filter(type_anomalie='duplicate_rib')
            if rib_dupes.exists():
                recommandations_prioritaires.append({
                    'priorite': 'ELEVEE',
                    'titre': f"{rib_dupes.count()} RIB dupliqué(s) détecté(s)",
                    'action': "Contrôle des comptes bancaires",
                    'details': "Vérifier la légitimité des comptes partagés"
                })

            # Recommandations générales
            recommandations_generales = []

            taux_anomalies = session.get_taux_anomalies()
            if taux_anomalies > 15:
                recommandations_generales.append(
                    "Taux d'anomalies élevé (>15%) - Révision des processus de paie recommandée"
                )
            elif taux_anomalies > 10:
                recommandations_generales.append(
                    "Taux d'anomalies modéré (>10%) - Surveillance renforcée conseillée"
                )

            if session.nb_heures_excessives > 0:
                recommandations_generales.append(
                    "Heures excessives détectées - Vérifier le respect du droit du travail"
                )

            return {
                'session': {
                    'nom': session.nom_session,
                    'date': session.date_completion,
                    'taux_anomalies': taux_anomalies
                },
                'resume': {
                    'total_employes': session.nb_lignes_analysees,
                    'total_anomalies': session.nb_anomalies_detectees,
                    'risques_critiques': critiques.count()
                },
                'analyse_par_type': analyse_types,
                'recommandations_prioritaires': recommandations_prioritaires,
                'recommandations_generales': recommandations_generales,
                'plan_action': generer_plan_action(analyse_types)
            }
