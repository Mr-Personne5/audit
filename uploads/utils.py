import pandas as pd
import logging
from django.core.exceptions import ValidationError
import unicodedata
from difflib import SequenceMatcher

from .models import FichierImporte, PreviewData, MappingColonne


logger = logging.getLogger('auditia')


class FileProcessor:
    """Classe pour traiter et analyser les fichiers uploadés"""

    # Colonnes obligatoires par type de fichier
    COLONNES_OBLIGATOIRES = {
        'paie': ['matricule', 'nom', 'prenom', 'salaire_brut'],
        'liste_personnel': ['matricule', 'nom', 'prenom', 'poste'],
        'grille': ['poste', 'niveau', 'salaire_min', 'salaire_max'],
        'convention': ['type_prime', 'montant', 'condition'],
        'procedure': ['regle', 'description']
    }

    # Colonnes optionnelles mais recommandées pour les fichiers de paie
    COLONNES_RECOMMANDEES = {
        'paie': [
            'matricule', 'nom', 'prenom', 'genre', 'numero_compte', 'directions', 
            'departement', 'poste', 'statut', 'lieu_emploi', 'date_embauche', 
            'anciennete', 'date_naissance', 'age', 'classe_salariale', 
            'categorie_salariale', 'salaire_brut', 'heures_travaillees', 
            'primes', 'retenues', 'montant_total', 'date_paie', 'annees_retraite'
        ]
    }

    @staticmethod
    def lire_fichier(fichier_obj):
        """Lit un fichier CSV ou Excel et retourne un DataFrame"""
        try:
            extension = fichier_obj.get_file_extension()

            if extension == '.csv':
                # Essayer différents encodages
                encodages = ['utf-8', 'latin-1', 'cp1252']
                for encoding in encodages:
                    try:
                        df = pd.read_csv(fichier_obj.fichier.path, encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise ValidationError("Impossible de lire le fichier CSV avec les encodages disponibles")

            elif extension in ['.xlsx', '.xls']:
                df = pd.read_excel(fichier_obj.fichier.path)

            else:
                raise ValidationError("Format de fichier non supporté")

            # Nettoyer les noms de colonnes mais garder la casse originale pour l'affichage
            colonnes_originales = df.columns.tolist()
            df.columns = [col.strip() for col in colonnes_originales]  # Juste supprimer les espaces

            return df

        except Exception as e:
            logger.error(f"Erreur lors de la lecture du fichier {fichier_obj.id}: {str(e)}")
            raise ValidationError(f"Erreur lors de la lecture: {str(e)}")

    @staticmethod
    def analyser_fichier(fichier_obj):
        """Analyse un fichier et crée un aperçu"""
        try:
            df = FileProcessor.lire_fichier(fichier_obj)

            # Garder les noms de colonnes originaux (pas de conversion en minuscules)
            # df.columns = df.columns.str.strip().str.lower()  # SUPPRIMÉ

            # Mettre à jour le statut
            fichier_obj.status = 'processing'
            fichier_obj.nb_lignes = len(df)
            fichier_obj.colonnes_detectees = df.columns.tolist()
            fichier_obj.save()

            # Vérifier les colonnes obligatoires avec mapping automatique
            colonnes_obligatoires = FileProcessor.COLONNES_OBLIGATOIRES.get(
                fichier_obj.type_fichier, []
            )
            
            # Proposer un mapping automatique
            mapping_propose = FileProcessor.proposer_mapping_colonnes(fichier_obj)
            
            # Debug: logger le mapping proposé
            logger.info(f"Mapping proposé pour fichier {fichier_obj.id}: {mapping_propose}")
            logger.info(f"Colonnes détectées: {fichier_obj.colonnes_detectees}")
            
            # Vérifier si les colonnes obligatoires sont présentes via le mapping
            colonnes_manquantes = []
            for col_obligatoire in colonnes_obligatoires:
                if col_obligatoire not in mapping_propose:
                    colonnes_manquantes.append(col_obligatoire)

            if colonnes_manquantes:
                erreur = f"Colonnes manquantes: {', '.join(colonnes_manquantes)}. Colonnes détectées: {', '.join(df.columns.tolist())}. Mapping proposé: {mapping_propose}"
                fichier_obj.erreurs_processing = erreur
                fichier_obj.status = 'error'
                fichier_obj.save()
                return False, erreur

            # Créer l'aperçu (10 premières lignes)
            apercu_data = df.head(10).fillna('').to_dict('records')

            # Sauvegarder l'aperçu
            preview, created = PreviewData.objects.get_or_create(
                fichier=fichier_obj,
                defaults={
                    'colonnes': df.columns.tolist(),
                    'donnees_echantillon': apercu_data,
                    'nb_total_lignes': len(df)
                }
            )

            if not created:
                preview.colonnes = df.columns.tolist()
                preview.donnees_echantillon = apercu_data
                preview.nb_total_lignes = len(df)
                preview.save()

            # Créer automatiquement les mappings proposés
            for col_attendue, col_fichier in mapping_propose.items():
                MappingColonne.objects.get_or_create(
                    fichier=fichier_obj,
                    colonne_attendue=col_attendue,
                    defaults={
                        'colonne_fichier': col_fichier,
                        'est_confirme': True
                    }
                )

            # Marquer comme traité
            fichier_obj.status = 'processed'
            fichier_obj.save()

            logger.info(f"Fichier {fichier_obj.id} analysé avec succès")
            return True, "Fichier analysé avec succès"

        except Exception as e:
            erreur = str(e)
            fichier_obj.erreurs_processing = erreur
            fichier_obj.status = 'error'
            fichier_obj.save()
            logger.error(f"Erreur lors de l'analyse du fichier {fichier_obj.id}: {erreur}")
            return False, erreur

    @staticmethod
    def proposer_mapping_colonnes(fichier_obj):
        """Propose un mapping automatique des colonnes"""
        if not fichier_obj.colonnes_detectees:
            return {}

        # Mapping étendu par similarité de noms pour les fichiers de paie
        mappings_communs = {
            'paie': {
                'matricule': ['matricule', 'Matricule', 'MATRICULE', 'matricule_employe', 'numero_matricule'],
                'nom': ['nom', 'noms', 'Nom', 'Noms', 'NOM', 'NOMS', 'nom_employe', 'nom_famille'],
                'prenom': ['prenom', 'prénom', 'prenoms', 'prénoms', 'Prenom', 'Prénom', 'Prenoms', 'Prénoms', 'PRENOM', 'PRENOMS'],
                'salaire_brut': ['salaire_brut', 'salaire brut', 'Salaire brut', 'SALAIRE BRUT', 'salairebrut', 'brut', 'Brut', 'salaire de base', 'Salaire de base', 'SALAIRE DE BASE', 'salaire_base', 'base', 'Base', 'BASE'],
                'montant_total': ['montant_total', 'montant total', 'salaire_net', 'salaire net', 'Salaire net', 'SALAIRE NET', 'salaire_net_a_payer', 'salaire net à payer', 'salaire net a payer', 'net', 'Net', 'montant_paye', 'montant payé', 'net à payer', 'Net à payer', 'NET À PAYER', 'net a payer', 'Net a payer', 'NET A PAYER'],
                'genre': ['genre', 'Genre', 'GENRE', 'sexe', 'Sexe', 'SEXE', 'gender'],
                'numero_compte': ['numero_compte', 'numéro de compte', 'Numéro de compte', 'compte', 'Compte', 'numero_compte_bancaire', 'compte bancaire', 'Compte bancaire', 'COMPTE BANCAIRE', 'banque', 'Banque', 'BANQUE'],
                'directions': ['directions', 'Directions', 'DIRECTIONS', 'direction', 'Direction', 'DIRECTION', 'service', 'Service', 'SERVICE'],
                'departement': ['département ou service', 'Département ou Service', 'departement', 'Département', 'DEPT', 'dept'],
                'poste': ['poste ou fonction', 'Poste ou fonction', 'poste', 'Poste', 'POSTE', 'fonction', 'Fonction', 'FONCTION'],
                'statut': ['statut employé', 'Statut Employé', 'statut', 'Statut', 'STATUT', 'type_contrat', 'type contrat', 'statut employé (cdd, cdi, expatrie)', 'Statut Employé (CDD, CDI, EXPATRIE)'],
                'lieu_emploi': ['lieu emploi', 'Lieu Emploi', 'lieu', 'Lieu', 'LIEU', 'site', 'Site', 'SITE'],
                'date_embauche': ['dates d\'embauche', 'Dates d\'Embauche', 'date_embauche', 'Date embauche', 'embauche', 'Embauche'],
                'anciennete': ['ancienneté', 'Ancienneté', 'anciennete', 'Anciennete', 'nb années', 'Nb années', 'annees', 'Années', 'ancienneté (nb années)', 'Ancienneté (Nb années)'],
                'date_naissance': ['date naissance', 'Date Naissance', 'naissance', 'Naissance', 'date_naissance', 'Date de naissance'],
                'age': ['ages', 'Ages', 'AGES', 'age', 'Age', 'AGE'],
                'classe_salariale': ['classe salariale', 'Classe salariale', 'classe', 'Classe', 'CLASSE'],
                'categorie_salariale': ['catégorie salariale', 'CATEGORIE salariale', 'categorie', 'Catégorie', 'CATEGORIE'],
                'heures_travaillees': ['heures travaillées', 'Heures travaillées', 'heures', 'Heures', 'HEURES'],
                'primes': ['primes ou avantages', 'Primes ou avantages', 'primes', 'Primes', 'PRIMES', 'avantages', 'Avantages', 'prime', 'Prime', 'PRIME'],
                'retenues': ['retenues', 'Retenues', 'RETENUES', 'impôts', 'Impôts', 'assurances', 'Assurances', 'retenues (impôts, assurances, autres)', 'Retenues (impôts, assurances, autres)', 'retenue', 'Retenue', 'RETENUE'],
                'date_paie': ['date de paie', 'Date de paie', 'date_paie', 'Date paie', 'mois_paie', 'Mois paie', 'date de paie (chronologiquement)', 'Date de paie (Chronologiquement)'],
                'annees_retraite': ['nombre années avant retraite', 'Nombre Années Avant Retraite', 'retraite', 'Retraite', 'annees_avant_retraite']
            },
            'liste_personnel': {
                'matricule': ['matricule', 'Matricule', 'MATRICULE', 'matricule_employe', 'numero_matricule', 'Identifiant employé', 'identifiant employé', 'Identifiant Employé'],
                'nom': ['nom', 'Nom', 'NOM', 'noms', 'Noms', 'NOMS', 'nom_employe', 'nom famille', 'Noms Employé', 'Noms employé', 'Noms Employés'],
                'prenom': ['prenom', 'Prenom', 'PRENOM', 'prénom', 'Prénom', 'PRENOM', 'prenoms', 'Prenoms', 'PRENOMS', 'prénoms', 'Prénoms', 'PRENOMS', 'prenom_employe', 'Prénoms Employé', 'Prénoms employé', 'Prénoms Employés'],
                'poste': ['poste', 'Poste', 'POSTE', 'poste_employe', 'fonction', 'Fonction', 'FONCTION', 'Poste/fonction', 'Poste/Fonction', 'poste ou fonction', 'Poste ou fonction'],
            },
        }

        type_fichier = fichier_obj.type_fichier
        if type_fichier not in mappings_communs:
            return {}

        colonnes_detectees = [col.lower() for col in fichier_obj.colonnes_detectees]
        mapping_propose = {}

        # Première passe : correspondance exacte
        for col_attendue, variations in mappings_communs[type_fichier].items():
            for variation in variations:
                if variation.lower() in colonnes_detectees:
                    # Trouver la colonne originale (avec la casse originale)
                    for col_originale in fichier_obj.colonnes_detectees:
                        if col_originale.lower() == variation.lower():
                            mapping_propose[col_attendue] = col_originale
                            break
                    if col_attendue in mapping_propose:
                        break

        # Deuxième passe : détection par similarité pour les colonnes non trouvées
        colonnes_restantes = [col for col in fichier_obj.colonnes_detectees 
                            if col.lower() not in [v.lower() for v in mapping_propose.values()]]
        
        for col_attendue, variations in mappings_communs[type_fichier].items():
            if col_attendue not in mapping_propose:
                # Chercher la meilleure correspondance par similarité
                meilleure_correspondance = None
                meilleur_score = 0
                
                for variation in variations:
                    colonnes_similaires = FileProcessor.detecter_colonnes_similaires(
                        variation, colonnes_restantes, seuil_similarite=0.7
                    )
                    
                    if colonnes_similaires and colonnes_similaires[0][1] > meilleur_score:
                        meilleure_correspondance = colonnes_similaires[0][0]
                        meilleur_score = colonnes_similaires[0][1]
                
                if meilleure_correspondance and meilleur_score >= 0.7:
                    mapping_propose[col_attendue] = meilleure_correspondance

        # Troisième passe : détection par mots-clés pour les colonnes encore manquantes
        colonnes_restantes = [col for col in fichier_obj.colonnes_detectees 
                            if col.lower() not in [v.lower() for v in mapping_propose.values()]]
        
        # Mapping par mots-clés pour les colonnes obligatoires manquantes
        mots_cles_mapping = {
            'salaire_brut': ['salaire', 'base', 'brut'],
            'matricule': ['matricule', 'identifiant', 'numero'],
            'nom': ['nom', 'noms'],
            'prenom': ['prenom', 'prénom', 'prenoms', 'prénoms'],
        }
        
        colonnes_obligatoires = FileProcessor.COLONNES_OBLIGATOIRES.get(type_fichier, [])
        for col_attendue in colonnes_obligatoires:
            if col_attendue not in mapping_propose and col_attendue in mots_cles_mapping:
                mots_cles = mots_cles_mapping[col_attendue]
                for col_restante in colonnes_restantes:
                    col_lower = col_restante.lower()
                    if any(mot_cle in col_lower for mot_cle in mots_cles):
                        mapping_propose[col_attendue] = col_restante
                        break

        return mapping_propose

    @staticmethod
    def normaliser_nom_colonne(nom_colonne):
        """Normalise un nom de colonne pour la comparaison"""
        if not nom_colonne:
            return ""
        
        # Convertir en minuscules et supprimer les espaces superflus
        nom_normalise = nom_colonne.lower().strip()
        
        # Supprimer les caractères spéciaux et accents
        nom_normalise = unicodedata.normalize('NFD', nom_normalise)
        nom_normalise = ''.join(c for c in nom_normalise if not unicodedata.combining(c))
        
        # Remplacer les espaces par des underscores
        nom_normalise = nom_normalise.replace(' ', '_')
        
        return nom_normalise

    @staticmethod
    def detecter_colonnes_similaires(colonne_cible, colonnes_disponibles, seuil_similarite=0.8):
        """Détecte les colonnes similaires en utilisant la similarité de chaînes"""
        colonnes_similaires = []
        
        for colonne in colonnes_disponibles:
            # Normaliser les deux colonnes
            norm_cible = FileProcessor.normaliser_nom_colonne(colonne_cible)
            norm_colonne = FileProcessor.normaliser_nom_colonne(colonne)
            
            # Calculer la similarité
            similarite = SequenceMatcher(None, norm_cible, norm_colonne).ratio()
            
            if similarite >= seuil_similarite:
                colonnes_similaires.append((colonne, similarite))
        
        # Trier par similarité décroissante
        colonnes_similaires.sort(key=lambda x: x[1], reverse=True)
        
        return colonnes_similaires
