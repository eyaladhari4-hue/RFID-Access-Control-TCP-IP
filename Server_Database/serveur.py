# ============================================================
#  Partie 4 — Serveur TCP central
#  Rôle : recevoir les requêtes JSON de la passerelle,
#         vérifier l'UID dans la base de données,
#         répondre GRANTED ou DENIED, logger chaque accès
#
#  Utilisation :
#    python serveur.py
# ============================================================

import socket
import json
import sqlite3
import threading
from datetime import datetime

# --- Configuration ---
HOST = "0.0.0.0"   # écoute sur toutes les interfaces
PORT = 5000
DB_FILE = "acces.db"


# ============================================================
#  Base de données SQLite
# ============================================================
def init_db():
    """
    Crée la base de données et les tables si elles n'existent pas.
    Table badges    : UIDs autorisés
    Table logs      : historique de tous les accès
    """
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()

    # Table des badges autorisés
    cur.execute('''
        CREATE TABLE IF NOT EXISTS badges (
            uid         TEXT PRIMARY KEY,
            nom         TEXT,
            role        TEXT,
            actif       INTEGER DEFAULT 1
        )
    ''')

    # Table des logs d'accès
    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         TEXT,
            room_id     TEXT,
            statut      TEXT,
            timestamp   TEXT,
            ip_client   TEXT
        )
    ''')

    # Insertion des badges autorisés (nos 2 cartes Wokwi)
    badges = [
        ("01020304", "Carte Bleue",  "employe"),
        ("11223344", "Carte Verte",  "employe"),
    ]
    cur.executemany('''
        INSERT OR IGNORE INTO badges (uid, nom, role) VALUES (?, ?, ?)
    ''', badges)

    conn.commit()
    conn.close()
    print(f"[DB] Base de données '{DB_FILE}' initialisée.")


def est_autorise(uid):
    """Vérifie si l'UID est dans la table badges et actif."""
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute("SELECT nom, role FROM badges WHERE uid=? AND actif=1", (uid,))
    resultat = cur.fetchone()
    conn.close()
    return resultat  # None si non autorisé, (nom, role) si autorisé


def logger_acces(uid, room_id, statut, timestamp, ip_client):
    """Enregistre chaque tentative d'accès dans la table logs."""
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute('''
        INSERT INTO logs (uid, room_id, statut, timestamp, ip_client)
        VALUES (?, ?, ?, ?, ?)
    ''', (uid, room_id, statut, timestamp, ip_client))
    conn.commit()
    conn.close()


def afficher_logs():
    """Affiche les 10 derniers accès enregistrés."""
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    lignes = cur.fetchall()
    conn.close()
    print("\n[DB] --- 10 derniers accès ---")
    for l in lignes:
        print(f"  {l}")
    print()


# ============================================================
#  Traitement d'un client TCP
# ============================================================
def traiter_client(conn, adresse):
    """
    Gère la connexion d'un client :
      1. Reçoit la requête JSON
      2. Vérifie l'UID en base
      3. Répond GRANTED ou DENIED
      4. Logue l'accès
    """
    ip_client = adresse[0]
    print(f"\n[SERVEUR] Connexion de {ip_client}:{adresse[1]}")

    try:
        # Réception de la requête
        donnees = conn.recv(1024).decode("utf-8").strip()
        if not donnees:
            return

        print(f"[SERVEUR] Requête reçue : {donnees}")
        requete = json.loads(donnees)

        uid       = requete.get("uid", "").upper()
        room_id   = requete.get("room_id", "INCONNU")
        timestamp = requete.get("timestamp", datetime.utcnow().isoformat() + "Z")

        # Vérification en base de données
        resultat = est_autorise(uid)

        if resultat:
            nom, role = resultat
            reponse = {
                "type":    "ACCESS_RESPONSE",
                "status":  "GRANTED",
                "code":    200,
                "message": f"Accès autorisé — {nom} ({role})"
            }
            statut = "GRANTED"
            print(f"[SERVEUR] GRANTED → UID={uid} | {nom} | {room_id}")
        else:
            reponse = {
                "type":    "ACCESS_RESPONSE",
                "status":  "DENIED",
                "code":    403,
                "message": "UID non reconnu ou badge désactivé"
            }
            statut = "DENIED"
            print(f"[SERVEUR] DENIED  → UID={uid} | {room_id}")

        # Envoi de la réponse
        conn.sendall((json.dumps(reponse) + "\n").encode("utf-8"))

        # Log en base de données
        logger_acces(uid, room_id, statut, timestamp, ip_client)

    except json.JSONDecodeError:
        print("[SERVEUR] Erreur : JSON invalide reçu")
        reponse = {"type": "ACCESS_RESPONSE", "status": "DENIED",
                   "code": 400, "message": "Format JSON invalide"}
        conn.sendall((json.dumps(reponse) + "\n").encode("utf-8"))

    except Exception as e:
        print(f"[SERVEUR] Erreur inattendue : {e}")

    finally:
        conn.close()
        afficher_logs()


# ============================================================
#  Boucle principale du serveur
# ============================================================
def demarrer_serveur():
    init_db()

    serveur = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveur.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serveur.bind((HOST, PORT))
    serveur.listen(5)

    print("========================================")
    print(" Serveur TCP RFID — Partie 4")
    print(f" Écoute sur {HOST}:{PORT}")
    print(" Badges autorisés : Carte Bleue, Carte Verte")
    print("========================================\n")

    while True:
        try:
            conn, adresse = serveur.accept()
            # Chaque client est géré dans un thread séparé
            thread = threading.Thread(
                target=traiter_client,
                args=(conn, adresse),
                daemon=True
            )
            thread.start()
        except KeyboardInterrupt:
            print("\n[SERVEUR] Arrêt du serveur.")
            break

    serveur.close()


if __name__ == "__main__":
    demarrer_serveur()