# ============================================================
#  MODULE : Détection d'anomalies + Alertes Email Gmail
#  À intégrer dans simulation_batiment.py
#
#  Fonctionnalités :
#    - Détecte 3 tentatives DENIED consécutives → alerte
#    - Bloque le badge 5 minutes après alerte
#    - Envoie un email Gmail à l'administrateur
#    - Affiche les badges bloqués dans l'interface
#
#  Configuration Gmail requise :
#    1. Active la validation en 2 étapes sur ton compte Gmail
#    2. Va sur : myaccount.google.com/apppasswords
#    3. Crée un "Mot de passe d'application" → copie les 16 caractères
#    4. Colle-le dans GMAIL_APP_PASSWORD ci-dessous
# ============================================================

import smtplib
import sqlite3
import threading
import time
from email.mime.text    import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
#  CONFIGURATION — À MODIFIER
# ============================================================
GMAIL_EXPEDITEUR  = "ton.email@gmail.com"       # Ton adresse Gmail
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"      # Mot de passe d'application Gmail
EMAIL_ADMIN        = "admin@exemple.com"         # Email qui reçoit les alertes

SEUIL_ANOMALIE     = 3      # Nombre de DENIED avant alerte
DUREE_BLOCAGE_MIN  = 5      # Minutes de blocage après alerte


# ============================================================
#  GESTIONNAIRE D'ANOMALIES
# ============================================================
class GestionnaireAnomalies:
    def __init__(self, callback_ui=None):
        """
        callback_ui : fonction appelée pour mettre à jour l'interface
                      signature : callback_ui(uid, evenement, details)
        """
        self.compteurs  = defaultdict(int)   # uid → nb tentatives échouées
        self.bloques    = {}                 # uid → datetime de fin de blocage
        self.callback_ui = callback_ui
        self._lock = threading.Lock()

    def est_bloque(self, uid):
        """Retourne True si le badge est actuellement bloqué."""
        with self._lock:
            if uid in self.bloques:
                if datetime.now() < self.bloques[uid]:
                    restant = (self.bloques[uid] - datetime.now()).seconds // 60
                    return True, restant
                else:
                    # Blocage expiré → on libère
                    del self.bloques[uid]
                    self.compteurs[uid] = 0
            return False, 0

    def enregistrer_tentative(self, uid, statut, batiment, etage):
        """
        Enregistre une tentative d'accès.
        Si DENIED → incrémente le compteur.
        Si compteur >= SEUIL → alerte + blocage.
        Si GRANTED → remet le compteur à zéro.
        """
        with self._lock:
            if statut == "GRANTED":
                self.compteurs[uid] = 0
                return

            self.compteurs[uid] += 1
            count = self.compteurs[uid]

            details = f"Bât. {batiment} — {etage} — Tentative {count}/{SEUIL_ANOMALIE}"

            if self.callback_ui:
                self.callback_ui(uid, "TENTATIVE_ECHOUEE", details)

            # Seuil atteint → alerte
            if count >= SEUIL_ANOMALIE:
                self.compteurs[uid] = 0
                fin_blocage = datetime.now() + timedelta(minutes=DUREE_BLOCAGE_MIN)
                self.bloques[uid] = fin_blocage

                if self.callback_ui:
                    self.callback_ui(uid, "ALERTE_DECLENCHEE",
                                     f"Badge bloqué {DUREE_BLOCAGE_MIN} min — {batiment}/{etage}")

                # Envoi email dans un thread séparé (ne bloque pas l'interface)
                threading.Thread(
                    target=self._envoyer_alerte_email,
                    args=(uid, batiment, etage, fin_blocage),
                    daemon=True
                ).start()

    def get_badges_bloques(self):
        """Retourne la liste des badges actuellement bloqués."""
        with self._lock:
            result = []
            maintenant = datetime.now()
            for uid, fin in list(self.bloques.items()):
                if maintenant < fin:
                    restant = int((fin - maintenant).total_seconds() // 60)
                    result.append((uid, restant))
                else:
                    del self.bloques[uid]
            return result

    # ── Envoi de l'email d'alerte ────────────────────────────
    def _envoyer_alerte_email(self, uid, batiment, etage, fin_blocage):
        """
        Envoie un email d'alerte à l'administrateur via Gmail SMTP.
        """
        now_str     = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
        blocage_str = fin_blocage.strftime("%H:%M:%S")

        sujet = f"[ALERTE RFID] Intrusion détectée — Badge {uid}"

        corps_html = f"""
        <html><body style="font-family: Arial, sans-serif; background: #f4f4f4; padding: 20px;">
          <div style="max-width:600px; margin:auto; background:white;
                      border-radius:8px; overflow:hidden; box-shadow:0 2px 8px #ccc;">

            <div style="background:#c0392b; padding:20px; color:white;">
              <h2 style="margin:0;">⚠ ALERTE SÉCURITÉ RFID</h2>
              <p style="margin:4px 0 0;">Tentatives d'accès non autorisées répétées</p>
            </div>

            <div style="padding:24px;">
              <table style="width:100%; border-collapse:collapse;">
                <tr style="background:#fdf2f2;">
                  <td style="padding:10px; font-weight:bold; color:#c0392b; width:40%;">Badge UID</td>
                  <td style="padding:10px; font-family:monospace;">{uid}</td>
                </tr>
                <tr>
                  <td style="padding:10px; font-weight:bold;">Bâtiment</td>
                  <td style="padding:10px;">Bâtiment {batiment}</td>
                </tr>
                <tr style="background:#fdf2f2;">
                  <td style="padding:10px; font-weight:bold;">Étage</td>
                  <td style="padding:10px;">{etage}</td>
                </tr>
                <tr>
                  <td style="padding:10px; font-weight:bold;">Date / Heure</td>
                  <td style="padding:10px;">{now_str}</td>
                </tr>
                <tr style="background:#fdf2f2;">
                  <td style="padding:10px; font-weight:bold;">Tentatives</td>
                  <td style="padding:10px; color:#c0392b; font-weight:bold;">
                    {SEUIL_ANOMALIE} tentatives échouées consécutives
                  </td>
                </tr>
                <tr>
                  <td style="padding:10px; font-weight:bold;">Badge bloqué jusqu'à</td>
                  <td style="padding:10px; color:#e67e22; font-weight:bold;">{blocage_str}</td>
                </tr>
              </table>

              <div style="margin-top:20px; padding:14px; background:#fef9e7;
                          border-left:4px solid #f39c12; border-radius:4px;">
                <p style="margin:0; color:#7d6608;">
                  <strong>Action recommandée :</strong> Vérifiez les caméras de surveillance
                  du bâtiment {batiment}, étage {etage}. Le badge a été automatiquement
                  bloqué pendant {DUREE_BLOCAGE_MIN} minutes.
                </p>
              </div>
            </div>

            <div style="background:#ecf0f1; padding:12px; text-align:center;
                        font-size:12px; color:#7f8c8d;">
              Système de contrôle d'accès RFID — Alerte automatique
            </div>
          </div>
        </body></html>
        """

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = sujet
            msg["From"]    = GMAIL_EXPEDITEUR
            msg["To"]      = EMAIL_ADMIN
            msg.attach(MIMEText(corps_html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_EXPEDITEUR, GMAIL_APP_PASSWORD)
                server.sendmail(GMAIL_EXPEDITEUR, EMAIL_ADMIN, msg.as_string())

            print(f"[EMAIL] Alerte envoyée à {EMAIL_ADMIN} pour badge {uid}")

        except smtplib.SMTPAuthenticationError:
            print("[EMAIL] ERREUR : Authentification Gmail échouée.")
            print("        → Vérifiez GMAIL_APP_PASSWORD (mot de passe d'application).")
        except smtplib.SMTPException as e:
            print(f"[EMAIL] ERREUR SMTP : {e}")
        except Exception as e:
            print(f"[EMAIL] ERREUR inattendue : {e}")


# ============================================================
#  INTÉGRATION DANS simulation_batiment.py
# ============================================================
#
#  1. Importe ce module en haut de simulation_batiment.py :
#
#       from anomalie_email import GestionnaireAnomalies
#
#  2. Dans __init__ de AppBatiment, crée le gestionnaire :
#
#       self.anomalies = GestionnaireAnomalies(
#           callback_ui=self._on_anomalie
#       )
#
#  3. Dans _afficher_resultat, appelle le gestionnaire :
#
#       self.anomalies.enregistrer_tentative(uid, statut, bat, etage)
#
#  4. Dans _run_scan, vérifie si le badge est bloqué :
#
#       bloque, restant = self.anomalies.est_bloque(uid)
#       if bloque:
#           self.log(f"[SÉCURITÉ] Badge {uid} BLOQUÉ ({restant} min restantes)", "r")
#           self._afficher_resultat("DENIED", uid, bat, etage)
#           self._fin_scan()
#           return
#
#  5. Ajoute le callback UI :
#
#       def _on_anomalie(self, uid, evenement, details):
#           if evenement == "TENTATIVE_ECHOUEE":
#               self.log(f"[ANOMALIE] {details}", "y")
#           elif evenement == "ALERTE_DECLENCHEE":
#               self.log(f"[ALERTE]   {details}", "r")
#               self.log(f"[EMAIL]    Alerte envoyée à {EMAIL_ADMIN}", "r")
#
# ============================================================


# ============================================================
#  TEST STANDALONE (sans l'interface graphique)
# ============================================================
if __name__ == "__main__":
    print("=== Test du gestionnaire d'anomalies ===\n")

    def mon_callback(uid, evenement, details):
        print(f"  [{evenement}] UID={uid} — {details}")

    g = GestionnaireAnomalies(callback_ui=mon_callback)

    print("Simulation : 3 tentatives échouées pour badge AABBCCDD\n")
    for i in range(3):
        print(f"Tentative {i+1}...")
        g.enregistrer_tentative("AABBCCDD", "DENIED", "A", "Étage 3")
        time.sleep(0.5)

    print()
    bloque, restant = g.est_bloque("AABBCCDD")
    print(f"Badge bloqué : {bloque} — Restant : {restant} min")

    print("\nSimulation : badge autorisé remet le compteur à zéro")
    g.enregistrer_tentative("01020304", "DENIED", "A", "Étage 4")
    g.enregistrer_tentative("01020304", "DENIED", "A", "Étage 4")
    g.enregistrer_tentative("01020304", "GRANTED", "A", "RDC")
    g.enregistrer_tentative("01020304", "DENIED", "A", "Étage 4")
    print("Compteur remis à zéro après GRANTED — 1 seul DENIED enregistré")
