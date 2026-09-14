#!/usr/bin/env python
"""
Script pour corriger la détection d'anomalies avec une logique réaliste
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'audit_ia.settings')
django.setup()

from auditengine.models import SessionAudit, ResultatAudit
from django.db import transaction
from collections import defaultdict

def corriger_anomalies_realistes():
    """Corrige la détection d'anomalies avec une logique réaliste"""
    
    print("🔧 CORRECTION AVEC LOGIQUE RÉALISTE")
    print("=" * 60)
    
    try:
        session = SessionAudit.objects.get(pk=8)
        resultats = session.resultats.all()
        
        print(f"Session: {session.nom_session}")
        print(f"Total résultats: {resultats.count()}")
        
        with transaction.atomic():
            # Réinitialiser toutes les anomalies
            resultats.update(est_anomalie=False)
            
            # Analyser les données pour détecter les vraies anomalies
            anomalies_corrigees = 0
            
            # 1. Détecter les RIB dupliqués
            rib_counts = defaultdict(list)
            for resultat in resultats:
                if resultat.rib and resultat.rib.strip():
                    rib_counts[resultat.rib.strip()].append(resultat)
            
            # Marquer les RIB dupliqués
            for rib, resultats_rib in rib_counts.items():
                if len(resultats_rib) > 1:
                    for resultat in resultats_rib:
                        resultat.est_anomalie = True
                        resultat.type_anomalie = 'duplicate_rib'
                        resultat.save()
                        anomalies_corrigees += 1
            
            # 2. Détecter les employés fantômes (noms vides ou très courts)
            for resultat in resultats:
                if not resultat.est_anomalie:  # Ne pas reclasser les RIB dupliqués
                    nom = (resultat.nom or "").strip()
                    prenom = (resultat.prenom or "").strip()
                    
                    if len(nom) <= 2 or len(prenom) <= 2 or nom.lower() in ['nan', 'none', '']:
                        resultat.est_anomalie = True
                        resultat.type_anomalie = 'ghost_employee'
                        resultat.save()
                        anomalies_corrigees += 1
            
            # 3. Détecter les salaires anormaux (très élevés ou très faibles)
            salaires = [float(r.salaire_brut) for r in resultats if r.salaire_brut]
            if salaires:
                salaire_moyen = sum(salaires) / len(salaires)
                salaire_std = (sum((s - salaire_moyen) ** 2 for s in salaires) / len(salaires)) ** 0.5
                
                for resultat in resultats:
                    if not resultat.est_anomalie and resultat.salaire_brut:
                        salaire = float(resultat.salaire_brut)
                        # Anomalie si salaire > 2 écarts-types de la moyenne
                        if abs(salaire - salaire_moyen) > 2 * salaire_std:
                            resultat.est_anomalie = True
                            resultat.type_anomalie = 'salaire_anormal'
                            resultat.save()
                            anomalies_corrigees += 1
            
            # 4. Détecter les heures excessives
            for resultat in resultats:
                if not resultat.est_anomalie and resultat.heures_travaillees:
                    heures = resultat.heures_travaillees
                    if heures > 250:  # Plus de 250h par mois
                        resultat.est_anomalie = True
                        resultat.type_anomalie = 'heures_excessives'
                        resultat.save()
                        anomalies_corrigees += 1
            
            # 5. Détecter les primes anormales
            for resultat in resultats:
                if not resultat.est_anomalie and resultat.montant_primes:
                    prime = float(resultat.montant_primes)
                    salaire = float(resultat.salaire_brut) if resultat.salaire_brut else 0
                    if salaire > 0 and prime > salaire * 0.5:  # Prime > 50% du salaire
                        resultat.est_anomalie = True
                        resultat.type_anomalie = 'prime_anormale'
                        resultat.save()
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
            
            print(f"\n✅ ANOMALIES RÉALISTES DÉTECTÉES: {anomalies_corrigees}")
            print(f"📊 STATISTIQUES RÉALISTES:")
            print(f"   Total anomalies: {session.nb_anomalies_detectees}")
            print(f"   Salaires anormaux: {session.nb_salaires_anormaux}")
            print(f"   Employés fantômes: {session.nb_employes_fantomes}")
            print(f"   Primes anormales: {session.nb_primes_anormales}")
            print(f"   Heures excessives: {session.nb_heures_excessives}")
            print(f"   RIB dupliqués: {session.nb_rib_dupliques}")
            print(f"   Lignes normales: {session.nb_aucune_anomalie}")
            
            # Calculer le nouveau taux
            taux = session.get_taux_anomalies()
            print(f"\n📈 TAUX RÉALISTE D'ANOMALIES: {taux}%")
            
            print("\n✅ Détection réaliste terminée!")
            
    except SessionAudit.DoesNotExist:
        print("❌ Session 8 non trouvée")
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")

if __name__ == "__main__":
    corriger_anomalies_realistes()
