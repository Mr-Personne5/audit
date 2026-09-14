#!/usr/bin/env python3
"""
Script de test pour vérifier le mapping automatique des colonnes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
import django
django.setup()

from uploads.utils import FileProcessor

def test_mapping_automatique():
    """Test du mapping automatique avec les colonnes du fichier de paie"""
    
    # Colonnes du fichier de paie de l'utilisateur
    colonnes_fichier = [
        "Matricule",
        "Noms", 
        "Prénoms",
        "Genre",
        "Numéro de compte",
        "Directions",
        "Département ou Service",
        "Poste ou fonction",
        "Statut Employé (CDD, CDI, EXPATRIE)",
        "Lieu Emploi",
        "Dates d'Embauche",
        "Ancienneté (Nb années)",
        "Date Naissance",
        "AGES",
        "Classe salariale",
        "CATEGORIE salariale",
        "Salaire brut",
        "Heures travaillées",
        "Primes ou avantages",
        "Retenues (impôts, assurances, autres)",
        "Salaire net",
        "Date de paie (Chronologiquement)",
        "Nombre Années Avant Retraite"
    ]
    
    print("=== TEST DU MAPPING AUTOMATIQUE ===")
    print(f"Colonnes du fichier ({len(colonnes_fichier)}):")
    for i, col in enumerate(colonnes_fichier, 1):
        print(f"  {i:2d}. {col}")
    
    print("\n" + "="*50)
    
    # Créer un objet fichier simulé pour le test
    class FichierTest:
        def __init__(self, colonnes):
            self.colonnes_detectees = colonnes
            self.type_fichier = 'paie'
    
    fichier_test = FichierTest(colonnes_fichier)
    
    # Tester le mapping automatique
    mapping_propose = FileProcessor.proposer_mapping_colonnes(fichier_test)
    
    print("MAPPING PROPOSÉ (Colonnes obligatoires):")
    print("-" * 50)
    
    colonnes_attendues = [
        'matricule', 'nom', 'prenom', 'salaire_brut'  # Seulement les 4 colonnes obligatoires
    ]
    
    for col_attendue in colonnes_attendues:
        col_fichier = mapping_propose.get(col_attendue, "❌ NON TROVÉE")
        statut = "✅ MAPPÉE" if col_fichier != "❌ NON TROVÉE" else "❌ MANQUANTE"
        print(f"{col_attendue:20s} → {col_fichier:35s} {statut}")
    
    print("\n" + "="*50)
    
    # Statistiques
    nb_mappees = len([v for v in mapping_propose.values() if v != "❌ NON TROVÉE"])
    nb_attendues = len(colonnes_attendues)
    taux_reussite = (nb_mappees / nb_attendues) * 100
    
    print(f"STATISTIQUES (Colonnes obligatoires):")
    print(f"  - Colonnes obligatoires: {nb_attendues}")
    print(f"  - Colonnes mappées: {nb_mappees}")
    print(f"  - Taux de réussite: {taux_reussite:.1f}%")
    
    # Colonnes manquantes
    colonnes_manquantes = [col for col in colonnes_attendues if col not in mapping_propose]
    if colonnes_manquantes:
        print(f"\n❌ COLONNES OBLIGATOIRES MANQUANTES ({len(colonnes_manquantes)}):")
        for col in colonnes_manquantes:
            print(f"  - {col}")
    else:
        print(f"\n✅ TOUTES LES COLONNES OBLIGATOIRES SONT MAPPÉES !")
    
    # Afficher aussi toutes les colonnes optionnelles mappées
    print(f"\n" + "="*50)
    print("COLONNES OPTIONNELLES MAPPÉES:")
    print("-" * 40)
    
    colonnes_optionnelles = [
        'genre', 'numero_compte', 'directions', 'departement', 'poste', 'statut', 
        'lieu_emploi', 'date_embauche', 'anciennete', 'date_naissance', 'age', 
        'classe_salariale', 'categorie_salariale', 'heures_travaillees', 
        'primes', 'retenues', 'montant_total', 'date_paie', 'annees_retraite'
    ]
    
    for col_attendue in colonnes_optionnelles:
        col_fichier = mapping_propose.get(col_attendue, "❌ NON TROVÉE")
        if col_fichier != "❌ NON TROVÉE":
            print(f"{col_attendue:20s} → {col_fichier}")
    
    nb_optionnelles_mappees = len([col for col in colonnes_optionnelles if col in mapping_propose])
    print(f"\nColonnes optionnelles mappées: {nb_optionnelles_mappees}/{len(colonnes_optionnelles)}")
    
    # Test de normalisation
    print("\n" + "="*50)
    print("TEST DE NORMALISATION:")
    print("-" * 30)
    
    test_colonnes = ["Salaire brut", "Prénoms", "Département ou Service", "CATEGORIE salariale"]
    for col in test_colonnes:
        norm = FileProcessor.normaliser_nom_colonne(col)
        print(f"'{col}' → '{norm}'")
    
    # Test de détection de similarité
    print("\n" + "="*50)
    print("TEST DE DÉTECTION DE SIMILARITÉ:")
    print("-" * 40)
    
    colonnes_test = ["salaire_brut", "Salaire brut", "SALAIRE BRUT", "salairebrut"]
    colonnes_disponibles = ["Salaire brut", "Salaire net", "Montant total"]
    
    for col_test in colonnes_test:
        similaires = FileProcessor.detecter_colonnes_similaires(col_test, colonnes_disponibles, seuil_similarite=0.7)
        print(f"'{col_test}' → {similaires}")

if __name__ == "__main__":
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import IsolationForest
    import joblib
    import os

    # 1. Charger le CSV
    csv_path = "media/uploads/mission2/Djiba_admin/paie/unlabeled_data.csv"
    df = pd.read_csv(csv_path)

    # 2. Appliquer le mapping robuste
    class FichierTest:
        def __init__(self, colonnes):
            self.colonnes_detectees = colonnes
            self.type_fichier = 'paie'
    fichier_test = FichierTest(list(df.columns))
    mapping = FileProcessor.proposer_mapping_colonnes(fichier_test)
    # Renommer les colonnes
    df_renamed = df.rename(columns={v: k for k, v in mapping.items() if v in df.columns})

    # 3. Garder uniquement les colonnes numériques standards pour l'IF
    colonnes_numeriques = [
        'age', 'anciennete', 'salaire_brut', 'heures_travaillees',
        'primes', 'retenues', 'salaire_net', 'annees_retraite',
        'montant_total', 'montant_primes'
    ]
    features = df_renamed[[col for col in colonnes_numeriques if col in df_renamed.columns]].copy()
    features = features.replace([np.inf, -np.inf], 0).fillna(0)
    features = features.astype(float)

    # Conversion stricte en float
    for col in features.columns:
        features[col] = pd.to_numeric(features[col], errors='coerce')
    features = features.fillna(0)
    print('Types des features pour le MLP:')
    print(features.dtypes)

    # 4. Entraîner le modèle
    print(f"Réentraînement Isolation Forest sur {features.shape[0]} lignes, {features.shape[1]} features...")
    model = IsolationForest(contamination=0.1, random_state=42, n_estimators=100)
    model.fit(features)

    # 5. Sauvegarder le modèle
    out_path = os.path.join("ml_models", "model_iforest.pkl")
    joblib.dump(model, out_path)
    print(f"Modèle Isolation Forest sauvegardé dans {out_path}")

    # 6. Réentraînement MLP Classifier (démonstration avec labels fictifs)
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    # Générer des labels fictifs (ex: 0 = normal, 1 = anomalie)
    np.random.seed(42)
    y = np.random.choice(['aucune', 'salaire_anormal', 'prime_anormale', 'heures_excessives'], size=features.shape[0])

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('mlp', MLPClassifier(hidden_layer_sizes=(100, 50), max_iter=1000, random_state=42, early_stopping=False))
    ])
    print(f"Réentraînement MLP Classifier sur {features.shape[0]} lignes, {features.shape[1]} features...")
    pipeline.fit(features, y)
    out_path_mlp = os.path.join("ml_models", "model_mlp.pkl")
    joblib.dump(pipeline, out_path_mlp)
    print(f"Modèle MLP Classifier sauvegardé dans {out_path_mlp}")

    # 7. Réentraînement MLP Classifier avec labels réels
    # Charger le fichier d'entraînement
    df_train = pd.read_csv("media/uploads/mon_fichier_entrainement.csv")
    df_train.rename(columns=lambda x: x.strip(), inplace=True)
    # Vérifier la colonne d'étiquette
    if 'anomaly_type' not in df_train.columns:
        raise ValueError("Le fichier d'entraînement doit contenir une colonne 'anomaly_type' !")

    # Colonnes numériques standardisées (mapping robuste)
    colonnes_numeriques = [
        'age', 'anciennete', 'salaire_brut', 'heures_travaillees',
        'primes', 'retenues', 'salaire_net', 'annees_retraite',
        'montant_total', 'montant_primes'
    ]
    features = df_train[[col for col in colonnes_numeriques if col in df_train.columns]].copy()
    for col in colonnes_numeriques:
        if col not in features.columns:
            features[col] = 0
    features = features[colonnes_numeriques]  # Assure l'ordre
    features = features.replace([np.inf, -np.inf], 0).fillna(0).astype(float)
    y = df_train['anomaly_type'].fillna('aucune').astype(str).apply(lambda x: x.strip() if isinstance(x, str) else 'aucune')
    y = y.apply(lambda x: x if x else 'aucune')
    print('Types uniques dans y :', set(type(x) for x in y))
    print('Valeurs uniques dans y :', y.unique())
    print('Nombre de NaN dans y :', y.isna().sum())
    print('Longueur des labels uniques :', [(val, len(val)) for val in y.unique()])
    print('Distribution des classes :', y.value_counts())

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('mlp', MLPClassifier(hidden_layer_sizes=(100, 50), max_iter=1000, random_state=42, early_stopping=False))
    ])
    print(f"Réentraînement MLP Classifier sur {features.shape[0]} lignes, {features.shape[1]} features...")
    pipeline.fit(features, y)
    out_path_mlp = os.path.join("ml_models", "model_mlp.pkl")
    joblib.dump(pipeline, out_path_mlp)
    print(f"Modèle MLP Classifier sauvegardé dans {out_path_mlp}") 