import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import StandardScaler, OneHotEncoder

class DataPrep(BaseEstimator, TransformerMixin):
    """
    - calcule missing_count et duplicate_count avant suppression des ID
    - supprime les colonnes identifiants (haute cardinalité)
    - encode les colonnes catégorielles low-cardinality
    - standardise les colonnes numériques
    """
    def __init__(self):
        # Liste des colonnes identifiants à exclure (haute cardinalité)
        self.id_cols = [
            'Matricule','Noms','Prénoms','Numéro de compte',
            "Dates d'Embauche","Date Naissance","Date de paie"
        ]
        # Liste des colonnes catégorielles à encoder
        self.cat_cols = [
            'Directions','Département/Service','Poste/fonction',
            'Statut Employé','Lieu Emploi','Classe salariale','CATEGORIE salariale'
        ]
        self.num_cols = []                                         # Populé en fit()
        self.scaler = StandardScaler()                             # Pour normalisation
        self.ohe = OneHotEncoder(sparse_output=False, handle_unknown='ignore')  # Pour catégorielles

    def fit(self, X, y=None):
        # Sélectionner colonnes numériques après retrait des ID
        df = X.drop(columns=self.id_cols, errors='ignore')
        self.num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        # Ajuster OneHotEncoder sur les colonnes CAT existantes
        cats = [c for c in self.cat_cols if c in X.columns]
        self.ohe.fit(X[cats].fillna('NA'))
        # Ajuster le scaler sur les données numériques
        self.scaler.fit(df[self.num_cols].fillna(0))
        return self

    def transform(self, X):
        df = X.copy()                                              # Copie des données brutes
        # 1) Comptage missing et doublons
        df['missing_count'] = df.isna().sum(axis=1)
        if {'Matricule','Numéro de compte'}.issubset(df.columns):
            dup_mask = df.duplicated(subset=['Matricule','Numéro de compte'], keep=False)
            df['duplicate_count'] = dup_mask.astype(int)
        else:
            df['duplicate_count'] = 0
        # 2) Retirer colonnes identifiants
        df_num = df.drop(columns=self.id_cols, errors='ignore')
        # 3) Normaliser colonnes numériques
        num_data = df_num[self.num_cols].fillna(0)
        X_num = self.scaler.transform(num_data)
        # 4) Encoder colonnes catégorielles
        cats = [c for c in self.cat_cols if c in df.columns]
        X_cat = self.ohe.transform(df[cats].fillna('NA')) if cats else np.empty((len(df),0))
        # 5) Concaténer numériques + catégorielles + compteurs
        extras = df[['missing_count','duplicate_count']].values
        return np.hstack([X_num, X_cat, extras])

    def fit_transform(self, X, y=None):
        return self.fit(X,y).transform(X) 