#!/usr/bin/env python
"""
Script pour corriger la détection d'anomalies dans la session 8
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import SessionAudit, ResultatAudit
from django.db import transaction

def corriger_detection_anomalies():
    """Corrige la détection d'anomalies dans la session 8"""
    
    print("🔧 CORRECTION DE LA DÉTECTION D'ANOMALIES")
    print("=" * 60)
    
    try:
        session = SessionAudit.objects.get(pk=8)
        resultats = session.resultats.all()
        
        print(f"Session: {session.nom_session}")
        print(f"Total résultats: {resultats.count()}")
        
        with transaction.atomic():
            # Réinitialiser toutes les anomalies
            resultats.update(est_anomalie=False)
            
            # Reclassifier correctement les anomalies
            anomalies_corrigees = 0
            
            for resultat in resultats:
                # Logique de détection d'anomalies corrigée
                est_anomalie = False
                
                # 1. Vérifier le score Isolation Forest
                if resultat.score_anomalie_if >= 0.7:  # Seuil plus strict
                    est_anomalie = True
                
                # 2. Vérifier le score MLP
                elif resultat.score_classification_mlp >= 0.6:
                    est_anomalie = True
                
                # 3. Vérifier les cas spéciaux
                elif resultat.type_anomalie in ['ghost_employee', 'duplicate_rib']:
                    # Ces types sont toujours des anomalies
                    est_anomalie = True
                
                # 4. Vérifier les valeurs extrêmes
                elif resultat.salaire_brut and float(resultat.salaire_brut) > 10000:
                    # Salaire très élevé
                    est_anomalie = True
                    resultat.type_anomalie = 'salaire_anormal'
                
                elif resultat.heures_travaillees and resultat.heures_travaillees > 200:
                    # Heures excessives
                    est_anomalie = True
                    resultat.type_anomalie = 'heures_excessives'
                
                # Mettre à jour le résultat
                resultat.est_anomalie = est_anomalie
                resultat.save()
                
                if est_anomalie:
                    anomalies_corrigees += 1
            
            # Mettre à jour les statistiques de la session
            vraies_anomalies = resultats.filter(est_anomalie=True)
            
            session.nb_anomalies_detectees = vraies_anomalies.count()
            session.nb_salaires_anormaux = vraies_anomalies.filter(type_anomalie='salaire_anormal').count()
            session.nb_employes_fantomes = vraies_anomalies.filter(type_anomalie='ghost_employee').count()
            session.nb_primes_anormales = vraies_anomalies.filter(type_anomalie='prime_anormale').count()
            session.nb_heures_excessives = vraies_anomalies.filter(type_anomalie='heures_excessives').count()
            session.nb_rib_dupliques = vraies_anomalies.filter(type_anomalie='duplicate_rib').count()
            session.nb_aucune_anomalie = resultats.filter(est_anomalie=False).count()
            
            session.save()
            
            print(f"\n✅ ANOMALIES CORRIGÉES: {anomalies_corrigees}")
            print(f"📊 NOUVELLES STATISTIQUES:")
            print(f"   Total anomalies: {session.nb_anomalies_detectees}")
            print(f"   Salaires anormaux: {session.nb_salaires_anormaux}")
            print(f"   Employés fantômes: {session.nb_employes_fantomes}")
            print(f"   Primes anormales: {session.nb_primes_anormales}")
            print(f"   Heures excessives: {session.nb_heures_excessives}")
            print(f"   RIB dupliqués: {session.nb_rib_dupliques}")
            print(f"   Lignes normales: {session.nb_aucune_anomalie}")
            
            # Calculer le nouveau taux
            taux = session.get_taux_anomalies()
            print(f"\n📈 NOUVEAU TAUX D'ANOMALIES: {taux}%")
            
            print("\n✅ Détection d'anomalies corrigée avec succès!")
            
    except SessionAudit.DoesNotExist:
        print("❌ Session 8 non trouvée")
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")

if __name__ == "__main__":
    corriger_detection_anomalies()
