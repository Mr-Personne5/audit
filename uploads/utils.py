import pandas as pd
import logging
from django.core.exceptions import ValidationError

from .models import FichierImporte, PreviewData


logger = logging.getLogger('auditia')


class FileProcessor:
    """Classe pour traiter et analyser les fichiers uploadés"""

    # Colonnes obligatoires par type de fichier
    COLONNES_OBLIGATOIRES = {
        'paie': ['matricule', 'nom', 'prenom', 'salaire_brut', 'montant_total'],
        'liste_personnel': ['matricule', 'nom', 'prenom', 'poste'],
        'grille': ['poste', 'niveau', 'salaire_min', 'salaire_max'],
        'convention': ['type_prime', 'montant', 'condition'],
        'procedure': ['regle', 'description']
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

            return df

        except Exception as e:
            logger.error(f"Erreur lors de la lecture du fichier {fichier_obj.id}: {str(e)}")
            raise ValidationError(f"Erreur lors de la lecture: {str(e)}")

    @staticmethod
    def analyser_fichier(fichier_obj):
        """Analyse un fichier et crée un aperçu"""
        try:
            df = FileProcessor.lire_fichier(fichier_obj)

            # Nettoyer les noms de colonnes
            df.columns = df.columns.str.strip().str.lower()

            # Mettre à jour le statut
            fichier_obj.status = 'processing'
            fichier_obj.nb_lignes = len(df)
            fichier_obj.colonnes_detectees = df.columns.tolist()
            fichier_obj.save()

            # Vérifier les colonnes obligatoires
            colonnes_obligatoires = FileProcessor.COLONNES_OBLIGATOIRES.get(
                fichier_obj.type_fichier, []
            )
            colonnes_manquantes = [
                col for col in colonnes_obligatoires
                if col not in df.columns
            ]

            if colonnes_manquantes:
                erreur = f"Colonnes manquantes: {', '.join(colonnes_manquantes)}"
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

        # Mapping basique par similarité de noms
        mappings_communs = {
            'paie': {
                'matricule': ['matricule', 'id', 'employee_id', 'emp_id'],
                'nom': ['nom', 'name', 'lastname', 'famille'],
                'prenom': ['prenom', 'firstname', 'first_name'],
                'salaire_brut': ['salaire_brut', 'gross_salary', 'salaire'],
                'montant_total': ['montant_total', 'total', 'net_pay']
            }
        }

        type_fichier = fichier_obj.type_fichier
        if type_fichier not in mappings_communs:
            return {}

        colonnes_detectees = [col.lower() for col in fichier_obj.colonnes_detectees]
        mapping_propose = {}

        for col_attendue, variations in mappings_communs[type_fichier].items():
            for variation in variations:
                if variation.lower() in colonnes_detectees:
                    mapping_propose[col_attendue] = variation
                    break

        return mapping_propose
