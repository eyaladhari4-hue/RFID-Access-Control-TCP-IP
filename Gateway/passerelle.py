# ============================================================
#  Partie 2 — Passerelle Python
#  Rôle : lire les logs Arduino (port série) et envoyer
#         les données au serveur TCP (Partie 4)
#
#  Dépendances : pip install pyserial
#
#  Utilisation :
#    python passerelle.py
#
#  En mode simulation (sans Arduino physique) :
#    python passerelle.py --simulation
# ============================================================

import socket
import json
import time
import argparse
from datetime import datetime

# --- Configuration ---
SERVEUR_IP   = "127.0.0.1"   # IP du serveur TCP (Partie 4)
SERVEUR_PORT = 5000            # Port du serveur TCP
PORT_SERIE   = "COM3"          # Port série Arduino (Windows: COM3, Linux: /dev/ttyUSB0)
BAUD_RATE    = 9600
TIMEOUT_TCP  = 5               # secondes avant timeout


# ============================================================
#  Connexion TCP vers le serveur
# ============================================================
def envoyer_requete(uid, timestamp, salle="SALLE_B12"):
    """
    Envoie une requête JSON au serveur TCP et retourne la réponse.
    Politique fail-close : si le serveur est injoignable → DENIED.
    """
    requete = {
        "type":      "ACCESS_REQUEST",
        "uid":       uid,
        "room_id":   salle,
        "timestamp": timestamp
    }

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_TCP)
        sock.connect((SERVEUR_IP, SERVEUR_PORT))

        # Envoi de la requête JSON
        message = json.dumps(requete) + "\n"
        sock.sendall(message.encode("utf-8"))
        print(f"[TCP] Requête envoyée  : {message.strip()}")

        # Réception de la réponse
        reponse_brute = sock.recv(1024).decode("utf-8").strip()
        reponse = json.loads(reponse_brute)
        print(f"[TCP] Réponse reçue    : {reponse_brute}")
        sock.close()
        return reponse

    except socket.timeout:
        print("[TCP] TIMEOUT — serveur injoignable")
        return {"type": "ACCESS_RESPONSE", "status": "DENIED", "code": 503, "message": "Serveur injoignable"}

    except ConnectionRefusedError:
        print("[TCP] ERREUR — connexion refusée")
        return {"type": "ACCESS_RESPONSE", "status": "DENIED", "code": 503, "message": "Connexion refusée"}

    except Exception as e:
        print(f"[TCP] ERREUR inattendue : {e}")
        return {"type": "ACCESS_RESPONSE", "status": "DENIED", "code": 500, "message": str(e)}


# ============================================================
#  Lecture du port série Arduino
# ============================================================
def lire_serie():
    """
    Lit le port série en continu et détecte les lignes [LOG].
    Format attendu : [LOG]   UID=XXXX | STATUT=GRANTED | ACTION=VERROU_OUVERT
    """
    try:
        import serial # type: ignore
    except ImportError:
        print("[ERREUR] Module 'serial' manquant. Lancez : pip install pyserial")
        return

    print(f"[SERIE] Connexion sur {PORT_SERIE} à {BAUD_RATE} bauds...")

    try:
        ser = serial.Serial(PORT_SERIE, BAUD_RATE, timeout=1)
        print("[SERIE] Connecté. En attente de logs Arduino...\n")

        while True:
            ligne = ser.readline().decode("utf-8", errors="ignore").strip()
            if not ligne:
                continue

            print(f"[SERIE] {ligne}")

            # Détecter une ligne de log
            if ligne.startswith("[LOG]"):
                traiter_log(ligne)

    except serial.SerialException as e:
        print(f"[SERIE] Erreur port série : {e}")


# ============================================================
#  Mode simulation (sans Arduino physique)
# ============================================================
def lire_simulation():
    """
    Simule des scans RFID pour tester la passerelle sans Arduino.
    Reproduit exactement le format de log de la Partie 1.
    """
    logs_simules = [
        "[LOG]   UID=01020304 | STATUT=GRANTED | ACTION=VERROU_OUVERT",
        "[LOG]   UID=11223344 | STATUT=GRANTED | ACTION=VERROU_OUVERT",
        "[LOG]   UID=55667788 | STATUT=DENIED | ACTION=ALERTE",
        "[LOG]   UID=01020304 | STATUT=GRANTED | ACTION=VERROU_OUVERT",
        "[LOG]   UID=AABBCCDD | STATUT=DENIED | ACTION=ALERTE",
    ]

    print("[SIM] Mode simulation activé")
    print("[SIM] Envoi de logs toutes les 3 secondes...\n")

    for log in logs_simules:
        print(f"[SERIE] {log}")
        traiter_log(log)
        time.sleep(3)

    print("\n[SIM] Simulation terminée.")


# ============================================================
#  Traitement d'une ligne de log Arduino
# ============================================================
def traiter_log(ligne):
    """
    Parse une ligne [LOG] et envoie la requête TCP au serveur.
    Format : [LOG]   UID=XXXX | STATUT=GRANTED | ACTION=VERROU_OUVERT
    """
    try:
        # Extraction de l'UID
        parties = ligne.replace("[LOG]", "").strip().split("|")
        uid     = parties[0].strip().replace("UID=", "")
        timestamp = datetime.utcnow().isoformat() + "Z"

        print(f"\n[PASSERELLE] UID extrait  : {uid}")
        print(f"[PASSERELLE] Timestamp    : {timestamp}")

        # Envoi au serveur TCP
        reponse = envoyer_requete(uid, timestamp)

        # Affichage du résultat final
        statut = reponse.get("status", "DENIED")
        if statut == "GRANTED":
            print(f"[RESULTAT] ACCES ACCORDE pour UID {uid}")
        else:
            print(f"[RESULTAT] ACCES REFUSE  pour UID {uid} — {reponse.get('message','')}")
        print()

    except Exception as e:
        print(f"[PASSERELLE] Erreur parsing log : {e}")


# ============================================================
#  Point d'entrée
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Passerelle RFID → Serveur TCP")
    parser.add_argument("--simulation", action="store_true",
                        help="Mode simulation sans Arduino physique")
    args = parser.parse_args()

    print("========================================")
    print(" Passerelle RFID — Partie 2")
    print(f" Serveur cible : {SERVEUR_IP}:{SERVEUR_PORT}")
    print("========================================\n")

    if args.simulation:
        lire_simulation()
    else:
        lire_serie()