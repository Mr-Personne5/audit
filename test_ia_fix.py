#!/usr/bin/env python
"""
Script pour tester la correction de l'IA
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import SessionAudit
from auditengine.engine import AuditEngine

def test_ia_fix():
    """Test de la correction de l'IA"""
    
    print("=== TEST CORRECTION IA ===\n")
    
    # Trouver une session qui a échoué
    session_failed = SessionAudit.objects.filter(status='error').first()
    if not session_failed:
        print("Aucune session échouée trouvée")
        return
    
    print(f"Test avec la session {session_failed.id}: {session_failed.nom_session}")
    
    # Réinitialiser la session
    session_failed.status = 'pending'
    session_failed.erreurs = ''
    session_failed.logs_traitement = []
    session_failed.save()
    
    print("Session réinitialisée, lancement du test...")
    
    try:
        engine = AuditEngine(session_failed)
        
        # Test étape par étape
        print("Étape 1: Chargement des données...")
        engine._charger_donnees()
        print(f"  ✓ Données chargées: {len(engine.df_data)} lignes")
        print(f"  ✓ Colonnes: {list(engine.df_data.columns)}")
        
        print("Étape 2: Chargement des modèles...")
        engine._charger_modeles()
        print("  ✓ Modèles chargés avec succès")
        
        print("Étape 3: Préparation des features...")
        engine._preparer_features()
        print(f"  ✓ Features IF: {engine.features_if.shape}")
        print(f"  ✓ Features MLP: {engine.features_mlp.shape}")
        
        if engine.features_if.empty:
            print("  ✗ ERREUR: Features IF vides!")
            print(f"  Colonnes disponibles: {list(engine.df_data.columns)}")
            if hasattr(engine.model_if, 'feature_names_in_'):
                print(f"  Colonnes attendues par IF: {list(engine.model_if.feature_names_in_)}")
        else:
            print("  ✓ Features préparées avec succès")
            
            print("Étape 4: Test Isolation Forest...")
            scores_if = engine._executer_isolation_forest()
            print(f"  ✓ Isolation Forest: {len(scores_if)} résultats")
            
            print("Étape 5: Test MLP Classifier...")
            predictions_mlp = engine._executer_mlp_classifier(scores_if)
            print(f"  ✓ MLP Classifier: {len(predictions_mlp)} résultats")
            
            print("Étape 6: Génération recommandations...")
            recommandations = engine._generer_recommandations(predictions_mlp)
            print(f"  ✓ Recommandations: {len(recommandations)} générées")
            
            print("Étape 7: Sauvegarde résultats...")
            engine._sauvegarder_resultats(scores_if, predictions_mlp, recommandations)
            print("  ✓ Résultats sauvegardés")
            
            print("Étape 8: Calcul statistiques...")
            engine._calculer_statistiques()
            print("  ✓ Statistiques calculées")
            
            # Finaliser la session
            session_failed.status = 'completed'
            session_failed.save()
            print("  ✓ Session terminée avec succès!")
            
    except Exception as e:
        print(f"  ✗ ERREUR: {str(e)}")
        session_failed.status = 'error'
        session_failed.erreurs = str(e)
        session_failed.save()

if __name__ == "__main__":
    test_ia_fix() 