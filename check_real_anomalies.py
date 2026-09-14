#!/usr/bin/env python
"""
Script pour vérifier les vraies anomalies détectées dans la session 8
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import SessionAudit, ResultatAudit

def verifier_vraies_anomalies():
    """Vérifie les vraies anomalies détectées dans la session 8"""
    
    print("🔍 VÉRIFICATION DES VRAIES ANOMALIES")
    print("=" * 60)
    
    try:
        session = SessionAudit.objects.get(pk=8)
        resultats = session.resultats.all()
        
        print(f"Session: {session.nom_session}")
        print(f"Total lignes analysées: {resultats.count()}")
        
        # Vérifier les vraies anomalies (est_anomalie=True)
        vraies_anomalies = resultats.filter(est_anomalie=True)
        print(f"\n🚨 VRAIES ANOMALIES DÉTECTÉES: {vraies_anomalies.count()}")
        
        # Statistiques par type d'anomalie (seulement les vraies anomalies)
        stats_vraies = {
            'salaires_anormaux': vraies_anomalies.filter(type_anomalie='salaire_anormal').count(),
            'employes_fantomes': vraies_anomalies.filter(type_anomalie='ghost_employee').count(),
            'primes_anormales': vraies_anomalies.filter(type_anomalie='prime_anormale').count(),
            'heures_excessives': vraies_anomalies.filter(type_anomalie='heures_excessives').count(),
            'rib_dupliques': vraies_anomalies.filter(type_anomalie='duplicate_rib').count(),
        }
        
        # Statistiques par niveau de risque (seulement les vraies anomalies)
        stats_risque_vraies = {
            'critique': vraies_anomalies.filter(niveau_risque='critique').count(),
            'eleve': vraies_anomalies.filter(niveau_risque='eleve').count(),
            'moyen': vraies_anomalies.filter(niveau_risque='moyen').count(),
            'faible': vraies_anomalies.filter(niveau_risque='faible').count(),
        }
        
        print("\n📊 VRAIES ANOMALIES PAR TYPE:")
        for type_anom, count in stats_vraies.items():
            print(f"   {type_anom}: {count}")
        
        print("\n🎯 NIVEAUX DE RISQUE (VRAIES ANOMALIES):")
        for niveau, count in stats_risque_vraies.items():
            print(f"   {niveau}: {count}")
        
        # Vérifier les lignes normales
        lignes_normales = resultats.filter(est_anomalie=False)
        print(f"\n✅ LIGNES NORMALES: {lignes_normales.count()}")
        
        # Calculer le vrai taux d'anomalies
        taux_reel = (vraies_anomalies.count() / resultats.count()) * 100
        print(f"\n📈 TAUX RÉEL D'ANOMALIES: {taux_reel:.1f}%")
        
        # Afficher quelques exemples d'anomalies
        print(f"\n🔍 EXEMPLES D'ANOMALIES:")
        for anomalie in vraies_anomalies[:5]:
            print(f"   - {anomalie.nom} {anomalie.prenom}: {anomalie.type_anomalie} (risque: {anomalie.niveau_risque})")
        
    except SessionAudit.DoesNotExist:
        print("❌ Session 8 non trouvée")
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")

if __name__ == "__main__":
    verifier_vraies_anomalies()
