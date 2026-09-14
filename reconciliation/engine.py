import pandas as pd
import logging
from typing import Tuple, List, Dict, Any
from fuzzywuzzy import fuzz
from decimal import Decimal
from datetime import datetime

from .models import RapprochementSession, ResultatRapprochement
from uploads.utils import FileProcessor

logger = logging.getLogger('auditia')


class RapprochementEngine:
    """Moteur de rapprochement entre fichiers RH et Paie"""

    def __init__(self, session: RapprochementSession):
        self.session = session
        self.logs = []

    def executer_rapprochement(self) -> bool:
        """Exécute le rapprochement complet"""
        import time
        start_time = time.time()

        try:
            self.session.status = 'processing'
            self.session.date_traitement = datetime.now().replace(tzinfo=None)
            self.session.save()

            # 1. Charger les données
            df_rh, df_paie = self._charger_donnees()

            # 2. Nettoyer et normaliser
            df_rh_clean = self._nettoyer_donnees_rh(df_rh)
            df_paie_clean = self._nettoyer_donnees_paie(df_paie)

            # 3. Exécuter les rapprochements
            resultats = self._rapprocher_donnees(df_rh_clean, df_paie_clean)

            # 4. Sauvegarder les résultats
            self._sauvegarder_resultats(resultats)

            # 5. Calculer les statistiques
            self._calculer_statistiques()

            self.session.status = 'completed'
            self.session.date_completion = datetime.now().replace(tzinfo=None)
            self.session.logs_traitement = self.logs
            self.session.save()

            return True

        except Exception as e:
            self.session.status = 'error'
            self.session.erreurs = str(e)
            self.session.logs_traitement = self.logs
            self.session.save()
            logger.error(f"Erreur rapprochement session {self.session.id}: {str(e)}")
            return False

    def _charger_donnees(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Charge les données des fichiers RH et Paie"""
        self._log("Chargement des fichiers...")

        # Charger fichier RH (liste personnel)
        df_rh = FileProcessor.lire_fichier(self.session.fichier_liste_personnel)
        self._log(f"Fichier RH chargé: {len(df_rh)} lignes")

        # Charger fichier Paie
        df_paie = FileProcessor.lire_fichier(self.session.fichier_paie)
        self._log(f"Fichier Paie chargé: {len(df_paie)} lignes")

        return df_rh, df_paie

    def _nettoyer_donnees_rh(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie et normalise les données RH"""
        df_clean = df.copy()

        # Normaliser les noms de colonnes
        df_clean.columns = df_clean.columns.str.lower().str.strip()

        # Nettoyer les données
        for col in ['nom', 'prenom']:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].astype(str).str.strip().str.title()

        if 'matricule' in df_clean.columns:
            df_clean['matricule'] = df_clean['matricule'].astype(str).str.strip()

        # Ajouter un index pour traçabilité
        df_clean['ligne_origine'] = df_clean.index + 1

        return df_clean

    def _nettoyer_donnees_paie(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie et normalise les données Paie"""
        df_clean = df.copy()

        # Normaliser les noms de colonnes
        df_clean.columns = df_clean.columns.str.lower().str.strip()

        # Nettoyer les données
        for col in ['nom', 'prenom']:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].astype(str).str.strip().str.title()

        if 'matricule' in df_clean.columns:
            df_clean['matricule'] = df_clean['matricule'].astype(str).str.strip()

        # Convertir les montants en numérique
        for col in ['salaire_brut', 'montant_total']:
            if col in df_clean.columns:
                df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')

        # Ajouter un index pour traçabilité
        df_clean['ligne_origine'] = df_clean.index + 1

        return df_clean

    def _rapprocher_donnees(self, df_rh: pd.DataFrame, df_paie: pd.DataFrame) -> List[Dict[str, Any]]:
        """Exécute le rapprochement selon les critères prioritaires"""
        resultats = []
        employes_paie_matches = set()  # Index (df_paie) des lignes déjà rapprochées
        employes_rh_matches = set()  # Index (df_rh) des lignes déjà rapprochées

        self._log("Début du rapprochement...")

        # ÉTAPE 1: Rapprochement par matricule (priorité 1)
        resultats_matricule = self._rapprocher_par_matricule(
            df_rh, df_paie, employes_paie_matches, employes_rh_matches
        )
        resultats.extend(resultats_matricule)

        # ÉTAPE 2: Rapprochement par nom+prénom pour les non-matchés
        resultats_nom = self._rapprocher_par_nom_prenom(
            df_rh, df_paie, employes_paie_matches, employes_rh_matches
        )
        resultats.extend(resultats_nom)

        # ÉTAPE 3: Identifier les employés RH non payés
        resultats_non_payes = self._identifier_non_payes(df_rh, employes_rh_matches)
        resultats.extend(resultats_non_payes)

        # ÉTAPE 4: Identifier les employés payés non déclarés
        resultats_non_declares = self._identifier_non_declares(df_paie, employes_paie_matches)
        resultats.extend(resultats_non_declares)

        # ÉTAPE 5: Détecter les doublons de paie
        resultats_doublons = self._detecter_doublons_paie(df_paie, resultats)
        resultats.extend(resultats_doublons)

        self._log(f"Rapprochement terminé: {len(resultats)} résultats")
        return resultats

    def _rapprocher_par_matricule(self, df_rh: pd.DataFrame, df_paie: pd.DataFrame,
                                  employes_paie_matches: set, employes_rh_matches: set) -> List[Dict[str, Any]]:
        """Rapprochement par matricule (critère prioritaire)"""
        resultats = []

        if 'matricule' not in df_rh.columns or 'matricule' not in df_paie.columns:
            self._log("Colonne matricule manquante, rapprochement par matricule ignoré")
            return resultats

        for idx_rh, row_rh in df_rh.iterrows():
            matricule_rh = str(row_rh['matricule']).strip()
            if not matricule_rh or matricule_rh.lower() in ['nan', 'none', '']:
                continue

            # Chercher dans la paie
            matches_paie = df_paie[df_paie['matricule'].astype(str).str.strip() == matricule_rh]

            if len(matches_paie) == 1:
                # Match parfait
                row_paie = matches_paie.iloc[0]
                employes_paie_matches.add(row_paie.name)
                employes_rh_matches.add(idx_rh)

                resultat = self._creer_resultat_match(
                    row_rh, row_paie, 'parfait', 'matricule', 99.0
                )
                resultats.append(resultat)

            elif len(matches_paie) > 1:
                # Doublon détecté
                employes_rh_matches.add(idx_rh)
                for _, row_paie in matches_paie.iterrows():
                    employes_paie_matches.add(row_paie.name)

                    resultat = self._creer_resultat_match(
                        row_rh, row_paie, 'doublon', 'matricule', 95.0
                    )
                    resultat['commentaires'] = f"Doublon: {len(matches_paie)} paies pour le matricule {matricule_rh}"
                    resultats.append(resultat)

        self._log(f"Rapprochement matricule: {len(resultats)} matches trouvés")
        return resultats

    def _rapprocher_par_nom_prenom(self, df_rh: pd.DataFrame, df_paie: pd.DataFrame,
                                   employes_paie_matches: set, employes_rh_matches: set) -> List[Dict[str, Any]]:
        """Rapprochement par nom+prénom pour les employés RH non encore matchés"""
        resultats = []

        for idx_rh, row_rh in df_rh.iterrows():
            if idx_rh in employes_rh_matches:
                continue  # Déjà matché par matricule

            nom_rh = str(row_rh.get('nom', '')).strip().title()
            prenom_rh = str(row_rh.get('prenom', '')).strip().title()

            if not nom_rh or not prenom_rh:
                continue

            # Rechercher le MEILLEUR candidat dans la paie (employés non encore matchés)
            meilleur_score = None
            meilleur_idx_paie = None
            meilleur_row_paie = None

            for idx_paie, row_paie in df_paie.iterrows():
                if idx_paie in employes_paie_matches:
                    continue

                nom_paie = str(row_paie.get('nom', '')).strip().title()
                prenom_paie = str(row_paie.get('prenom', '')).strip().title()

                # Calcul de similarité
                score_nom = fuzz.ratio(nom_rh, nom_paie)
                score_prenom = fuzz.ratio(prenom_rh, prenom_paie)
                score_global = (score_nom + score_prenom) / 2

                if score_global >= 85 and (meilleur_score is None or score_global > meilleur_score):
                    meilleur_score = score_global
                    meilleur_idx_paie = idx_paie
                    meilleur_row_paie = row_paie

            if meilleur_score is not None:  # Seuil élevé pour éviter les faux positifs
                employes_paie_matches.add(meilleur_idx_paie)
                employes_rh_matches.add(idx_rh)

                resultat = self._creer_resultat_match(
                    row_rh, meilleur_row_paie, 'partiel', 'nom_prenom_ddn', meilleur_score
                )
                resultat['commentaires'] = f"Match nom/prénom (score: {meilleur_score:.1f}%)"
                resultats.append(resultat)

        self._log(f"Rapprochement nom/prénom: {len(resultats)} matches trouvés")
        return resultats

    def _identifier_non_payes(self, df_rh: pd.DataFrame, employes_rh_matches: set) -> List[Dict[str, Any]]:
        """Identifier les employés RH qui n'ont pas été payés"""
        resultats = []

        for idx_rh, row_rh in df_rh.iterrows():
            if idx_rh not in employes_rh_matches:
                matricule_rh = str(row_rh.get('matricule', '')).strip()
                resultat = {
                    'type_match': 'non_paye',
                    'critere_match': 'aucun',
                    'score_confiance': 0.0,
                    'matricule_rh': matricule_rh,
                    'nom_rh': str(row_rh.get('nom', '')),
                    'prenom_rh': str(row_rh.get('prenom', '')),
                    'poste_rh': str(row_rh.get('poste', '')),
                    'rib_rh': str(row_rh.get('rib', '')),
                    'salaire_prevu_rh': self._convertir_decimal(row_rh.get('salaire', 0)),
                    'ligne_rh': row_rh.get('ligne_origine'),
                    'commentaires': "Employé présent en RH mais non payé"
                }
                resultats.append(resultat)

        self._log(f"Employés non payés: {len(resultats)} identifiés")
        return resultats

    def _identifier_non_declares(self, df_paie: pd.DataFrame, employes_paie_matches: set) -> List[Dict[str, Any]]:
        """Identifier les employés payés mais non déclarés en RH"""
        resultats = []

        for idx_paie, row_paie in df_paie.iterrows():
            if idx_paie not in employes_paie_matches:
                resultat = {
                    'type_match': 'non_declare',
                    'critere_match': 'aucun',
                    'score_confiance': 0.0,
                    'matricule_paie': str(row_paie.get('matricule', '')),
                    'nom_paie': str(row_paie.get('nom', '')),
                    'prenom_paie': str(row_paie.get('prenom', '')),
                    'rib_paie': str(row_paie.get('rib', '')),
                    'salaire_brut_paie': self._convertir_decimal(row_paie.get('salaire_brut', 0)),
                    'montant_total_paie': self._convertir_decimal(row_paie.get('montant_total', 0)),
                    'ligne_paie': row_paie.get('ligne_origine'),
                    'commentaires': "Employé payé mais non déclaré en RH (risque fraude)"
                }
                resultats.append(resultat)

        self._log(f"Employés non déclarés: {len(resultats)} identifiés")
        return resultats

    def _detecter_doublons_paie(self, df_paie: pd.DataFrame, resultats_existants: List) -> List[Dict[str, Any]]:
        """Détecter les doublons de paie supplémentaires"""
        # Cette fonction peut être étendue pour détecter d'autres types de doublons
        # Pour l'instant, les doublons par matricule sont déjà gérés
        return []

    def _creer_resultat_match(self, row_rh, row_paie, type_match: str, critere: str, score: float) -> Dict[str, Any]:
        """Crée un résultat de rapprochement entre un employé RH et Paie"""
        salaire_prevu = self._convertir_decimal(row_rh.get('salaire', 0))
        salaire_paye = self._convertir_decimal(row_paie.get('montant_total', 0))

        ecart_salaire = None
        if salaire_prevu is not None and salaire_paye is not None:
            ecart_salaire = salaire_paye - salaire_prevu

        return {
            'type_match': type_match,
            'critere_match': critere,
            'score_confiance': score,
            'matricule_rh': str(row_rh.get('matricule', '')),
            'nom_rh': str(row_rh.get('nom', '')),
            'prenom_rh': str(row_rh.get('prenom', '')),
            'poste_rh': str(row_rh.get('poste', '')),
            'rib_rh': str(row_rh.get('rib', '')),
            'salaire_prevu_rh': salaire_prevu,
            'matricule_paie': str(row_paie.get('matricule', '')),
            'nom_paie': str(row_paie.get('nom', '')),
            'prenom_paie': str(row_paie.get('prenom', '')),
            'rib_paie': str(row_paie.get('rib', '')),
            'salaire_brut_paie': self._convertir_decimal(row_paie.get('salaire_brut', 0)),
            'montant_total_paie': salaire_paye,
            'ecart_salaire': ecart_salaire,
            'ligne_rh': row_rh.get('ligne_origine'),
            'ligne_paie': row_paie.get('ligne_origine'),
        }

    def _convertir_decimal(self, valeur) -> Decimal:
        """Convertit une valeur en Decimal pour stockage en base"""
        try:
            if pd.isna(valeur):
                return None
            return Decimal(str(valeur))
        except:
            return None

    def _sauvegarder_resultats(self, resultats: List[Dict[str, Any]]):
        """Sauvegarde les résultats en base de données"""
        self._log(f"Sauvegarde de {len(resultats)} résultats...")

        # Supprimer les anciens résultats
        ResultatRapprochement.objects.filter(session=self.session).delete()

        # Créer les nouveaux résultats
        for resultat_data in resultats:
            ResultatRapprochement.objects.create(
                session=self.session,
                **resultat_data
            )

    def _calculer_statistiques(self):
        """Calcule et sauvegarde les statistiques globales"""
        resultats = ResultatRapprochement.objects.filter(session=self.session)

        # Basé sur le numéro de ligne d'origine (pas le matricule, qui peut être vide
        # quand le rapprochement s'est fait par nom/prénom) pour ne pas sous-compter
        # les employés dont le matricule est manquant.
        self.session.nb_employes_rh = len({r.ligne_rh for r in resultats if r.ligne_rh is not None})
        self.session.nb_employes_payes = len({r.ligne_paie for r in resultats if r.ligne_paie is not None})
        self.session.nb_matches_parfaits = resultats.filter(type_match='parfait').count()
        self.session.nb_matches_partiels = resultats.filter(type_match='partiel').count()
        self.session.nb_non_payes = resultats.filter(type_match='non_paye').count()
        self.session.nb_non_declares = resultats.filter(type_match='non_declare').count()
        self.session.nb_doublons = resultats.filter(type_match='doublon').count()

        self._log(f"Statistiques calculées: {self.session.get_taux_rapprochement()}% de rapprochement")

    def _log(self, message: str):
        """Ajoute un message aux logs"""
        self.logs.append({
            'timestamp': datetime.now().replace(tzinfo=None).isoformat(),
            'message': message
        })
        logger.info(f"RapprochementEngine [{self.session.id}]: {message}")


