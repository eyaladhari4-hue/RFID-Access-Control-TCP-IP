# ============================================================
#  SIMULATION RFID — Multi-bâtiments + Anomalies + Email
#  Utilisation : python simulation_batiment.py
#  Dépendances : aucune (stdlib Python uniquement)
# ============================================================

import tkinter as tk
import socket, json, sqlite3, threading, time, smtplib
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime             import datetime, timedelta
from collections          import defaultdict

HOST = "127.0.0.1"
PORT = 5001
DB   = "rfid_batiment.db"

BATIMENTS = ["A", "B"]
ETAGES    = ["RDC", "Étage 1", "Étage 2", "Étage 3", "Étage 4"]

DROITS = {
    "01020304": {"label":"Carte Bleue",   "color":"#2196F3",
                 "batiments":["A"],       "etages":["RDC","Étage 1","Étage 2"]},
    "11223344": {"label":"Carte Verte",   "color":"#4CAF50",
                 "batiments":["A","B"],   "etages":["RDC","Étage 1","Étage 2","Étage 3","Étage 4"]},
    "55667788": {"label":"Carte Rouge",   "color":"#F44336",
                 "batiments":[],          "etages":[]},
    "AABBCCDD": {"label":"Badge Inconnu", "color":"#FF9800",
                 "batiments":[],          "etages":[]},
}

# ── Alertes email ────────────────────────────────────────────
GMAIL_EXPEDITEUR   = "eyaladhari4@gmail.com"
GMAIL_APP_PASSWORD = "ysleysfghwlmjrjm"
EMAIL_ADMIN        = "eyaladhari4@gmail.com"
SEUIL_ANOMALIE     = 3
DUREE_BLOCAGE_MIN  = 5

BG="\033[0m"; BG2="#16213e"; BG3="#0f3460"
VERT="#4CAF50"; ROUGE="#F44336"; JAUNE="#FFD54F"
BLEU="#2196F3"; CYAN="#00bcd4"; GRIS="#888888"; WHITE="#ffffff"
BGUI="#1a1a2e"

panne_reseau  = False
serveur_actif = True

# ============================================================
#  BASE DE DONNÉES
# ============================================================
def init_db():
    c = sqlite3.connect(DB)
    c.execute('''CREATE TABLE IF NOT EXISTS badges (
        uid TEXT PRIMARY KEY, nom TEXT, batiments TEXT, etages TEXT, actif INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT, batiment TEXT, etage TEXT, statut TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alertes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT, batiment TEXT, etage TEXT, timestamp TEXT, email_envoye INTEGER DEFAULT 0)''')
    data = [
        ("01020304","Carte Bleue",  "A",   "RDC,Étage 1,Étage 2"),
        ("11223344","Carte Verte",  "A,B", "RDC,Étage 1,Étage 2,Étage 3,Étage 4"),
    ]
    c.executemany("INSERT OR IGNORE INTO badges VALUES (?,?,?,?,1)", data)
    c.commit(); c.close()

def verifier_acces(uid, batiment, etage):
    c = sqlite3.connect(DB)
    r = c.execute("SELECT nom, batiments, etages FROM badges WHERE uid=? AND actif=1",(uid,)).fetchone()
    c.close()
    if not r: return False, None
    nom, bats_str, etages_str = r
    if batiment in bats_str.split(",") and etage in etages_str.split(","):
        return True, nom
    return False, nom

def log_db(uid, batiment, etage, statut):
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO logs (uid,batiment,etage,statut,timestamp) VALUES (?,?,?,?,?)",
              (uid, batiment, etage, statut, datetime.now().strftime("%H:%M:%S")))
    c.commit(); c.close()

def log_alerte_db(uid, batiment, etage, email_ok):
    c = sqlite3.connect(DB)
    c.execute("INSERT INTO alertes (uid,batiment,etage,timestamp,email_envoye) VALUES (?,?,?,?,?)",
              (uid, batiment, etage, datetime.now().strftime("%H:%M:%S"), 1 if email_ok else 0))
    c.commit(); c.close()

def get_logs():
    c = sqlite3.connect(DB)
    r = c.execute("SELECT uid,batiment,etage,statut,timestamp FROM logs ORDER BY id DESC LIMIT 10").fetchall()
    c.close(); return r

# ============================================================
#  GESTIONNAIRE D'ANOMALIES
# ============================================================
class GestionnaireAnomalies:
    def __init__(self, callback_ui=None):
        self.compteurs   = defaultdict(int)
        self.bloques     = {}
        self.callback_ui = callback_ui
        self._lock       = threading.Lock()

    def est_bloque(self, uid):
        with self._lock:
            if uid in self.bloques:
                if datetime.now() < self.bloques[uid]:
                    restant = int((self.bloques[uid]-datetime.now()).total_seconds()//60)+1
                    return True, restant
                else:
                    del self.bloques[uid]
                    self.compteurs[uid] = 0
            return False, 0

    def enregistrer(self, uid, statut, batiment, etage):
        with self._lock:
            if statut == "GRANTED":
                self.compteurs[uid] = 0
                return
            self.compteurs[uid] += 1
            count = self.compteurs[uid]
            if self.callback_ui:
                self.callback_ui(uid, "TENTATIVE",
                    f"Tentative échouée {count}/{SEUIL_ANOMALIE} — Bât.{batiment} {etage}")
            if count >= SEUIL_ANOMALIE:
                self.compteurs[uid] = 0
                fin = datetime.now() + timedelta(minutes=DUREE_BLOCAGE_MIN)
                self.bloques[uid] = fin
                if self.callback_ui:
                    self.callback_ui(uid, "ALERTE",
                        f"Badge bloqué {DUREE_BLOCAGE_MIN} min — Bât.{batiment} {etage}")
                threading.Thread(target=self._send_email,
                                 args=(uid,batiment,etage,fin), daemon=True).start()

    def get_bloques(self):
        with self._lock:
            now = datetime.now()
            result = []
            for uid, fin in list(self.bloques.items()):
                if now < fin:
                    result.append((uid, int((fin-now).total_seconds()//60)+1))
                else:
                    del self.bloques[uid]
            return result

    def _send_email(self, uid, batiment, etage, fin_blocage):
        try:
            now_str = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
            sujet   = f"[ALERTE RFID] Intrusion détectée — Badge {uid}"
            html    = f"""<html><body style="font-family:Arial;background:#f4f4f4;padding:20px">
            <div style="max-width:580px;margin:auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px #ccc">
              <div style="background:#c0392b;padding:20px;color:white">
                <h2 style="margin:0">⚠ ALERTE SÉCURITÉ RFID</h2>
                <p style="margin:4px 0 0">{SEUIL_ANOMALIE} tentatives d'accès non autorisées</p>
              </div>
              <div style="padding:24px">
                <table style="width:100%;border-collapse:collapse">
                  <tr style="background:#fdf2f2"><td style="padding:10px;font-weight:bold;color:#c0392b;width:40%">Badge UID</td><td style="padding:10px;font-family:monospace">{uid}</td></tr>
                  <tr><td style="padding:10px;font-weight:bold">Bâtiment</td><td style="padding:10px">Bâtiment {batiment}</td></tr>
                  <tr style="background:#fdf2f2"><td style="padding:10px;font-weight:bold">Étage</td><td style="padding:10px">{etage}</td></tr>
                  <tr><td style="padding:10px;font-weight:bold">Date / Heure</td><td style="padding:10px">{now_str}</td></tr>
                  <tr style="background:#fdf2f2"><td style="padding:10px;font-weight:bold">Badge bloqué jusqu'à</td><td style="padding:10px;color:#e67e22;font-weight:bold">{fin_blocage.strftime("%H:%M:%S")}</td></tr>
                </table>
                <div style="margin-top:16px;padding:12px;background:#fef9e7;border-left:4px solid #f39c12;border-radius:4px">
                  <p style="margin:0;color:#7d6608"><strong>Action :</strong> Vérifiez les caméras du Bâtiment {batiment}, {etage}. Badge bloqué {DUREE_BLOCAGE_MIN} min automatiquement.</p>
                </div>
              </div>
              <div style="background:#ecf0f1;padding:10px;text-align:center;font-size:12px;color:#7f8c8d">Système RFID — Alerte automatique</div>
            </div></body></html>"""

            msg = MIMEMultipart("alternative")
            msg["Subject"] = sujet
            msg["From"]    = GMAIL_EXPEDITEUR
            msg["To"]      = EMAIL_ADMIN
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                srv.login(GMAIL_EXPEDITEUR, GMAIL_APP_PASSWORD)
                srv.sendmail(GMAIL_EXPEDITEUR, EMAIL_ADMIN, msg.as_string())

            log_alerte_db(uid, batiment, etage, True)
            if self.callback_ui:
                self.callback_ui(uid, "EMAIL_OK", f"Alerte envoyée à {EMAIL_ADMIN}")

        except smtplib.SMTPAuthenticationError:
            log_alerte_db(uid, batiment, etage, False)
            if self.callback_ui:
                self.callback_ui(uid, "EMAIL_ERR",
                    "Auth Gmail échouée → vérifiez GMAIL_APP_PASSWORD")
        except Exception as e:
            log_alerte_db(uid, batiment, etage, False)
            if self.callback_ui:
                self.callback_ui(uid, "EMAIL_ERR", str(e))

# ============================================================
#  SERVEUR TCP
# ============================================================
def traiter_client(conn, addr):
    try:
        data = conn.recv(1024).decode().strip()
        req  = json.loads(data)
        uid  = req.get("uid","").upper()
        bat  = req.get("batiment","")
        eta  = req.get("etage","")
        ok, nom = verifier_acces(uid, bat, eta)
        if ok:
            rep = {"status":"GRANTED","code":200,"message":f"Accès autorisé — {nom}"}
        else:
            rep = {"status":"DENIED","code":403,"message":"Accès refusé"}
        conn.sendall((json.dumps(rep)+"\n").encode())
        log_db(uid, bat, eta, rep["status"])
    except: pass
    finally: conn.close()

def demarrer_serveur():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT)); srv.listen(10); srv.settimeout(1)
    while serveur_actif:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=traiter_client, args=(conn,addr), daemon=True).start()
        except: continue
    srv.close()

# ============================================================
#  INTERFACE GRAPHIQUE
# ============================================================
class AppBatiment:
    def __init__(self, root):
        self.root   = root
        self.root.title("Simulation RFID — Multi-bâtiments + Sécurité")
        self.root.configure(bg=BGUI)
        self.root.resizable(False, False)

        self.scanning           = False
        self.bat_sel            = tk.StringVar(value="A")
        self.etage_sel          = tk.StringVar(value="RDC")
        self.cellules           = {}
        self.anomalies          = GestionnaireAnomalies(callback_ui=self._on_anomalie)

        self._build_ui()
        threading.Thread(target=demarrer_serveur, daemon=True).start()
        time.sleep(0.3)
        self.log("[SERVEUR] Démarré sur port 5001", VERT)
        self.log(f"[SÉCURITÉ] Seuil anomalie : {SEUIL_ANOMALIE} tentatives", JAUNE)
        self.log(f"[EMAIL]    Alertes → {EMAIL_ADMIN}", CYAN)

    # ── UI ───────────────────────────────────────────────────
    def _build_ui(self):
        tk.Label(self.root, text="CONTRÔLE D'ACCÈS RFID — SÉCURITÉ AVANCÉE",
                 bg=BGUI, fg="#e94560", font=("Consolas",13,"bold")).grid(
                 row=0, column=0, columnspan=3, pady=(12,2))
        tk.Label(self.root,
                 text="Multi-bâtiments · Droits par étage · Détection anomalies · Alertes email",
                 bg=BGUI, fg=GRIS, font=("Consolas",9)).grid(
                 row=1, column=0, columnspan=3, pady=(0,8))

        # Colonne gauche : bâtiments
        left = tk.Frame(self.root, bg=BGUI)
        left.grid(row=2, column=0, padx=12, pady=4, sticky="n")
        for bat in BATIMENTS:
            color = CYAN if bat=="A" else "#FF9800"
            tk.Label(left, text=f"BÂTIMENT {bat}", bg=BGUI, fg=color,
                     font=("Consolas",10,"bold")).pack(pady=(0,3))
            cv = self._creer_batiment(left, bat)
            cv.pack(pady=(0,14))

        # Colonne centrale
        mid = tk.Frame(self.root, bg=BGUI)
        mid.grid(row=2, column=1, padx=12, pady=4, sticky="n")

        tk.Label(mid, text="SÉLECTION", bg=BGUI, fg=GRIS,
                 font=("Consolas",9,"bold")).pack()
        tk.Label(mid, text="Bâtiment :", bg=BGUI, fg=WHITE,
                 font=("Consolas",10)).pack(anchor="w", pady=(8,2))
        bf = tk.Frame(mid, bg=BGUI); bf.pack(fill="x")
        for bat in BATIMENTS:
            tk.Radiobutton(bf, text=f"Bât. {bat}", variable=self.bat_sel, value=bat,
                           bg=BGUI, fg=WHITE, selectcolor=BG3, activebackground=BGUI,
                           font=("Consolas",10),
                           command=self._highlight).pack(side="left", padx=8)

        tk.Label(mid, text="Étage :", bg=BGUI, fg=WHITE,
                 font=("Consolas",10)).pack(anchor="w", pady=(10,2))
        ef = tk.Frame(mid, bg=BGUI); ef.pack(fill="x")
        for i, e in enumerate(ETAGES):
            tk.Radiobutton(ef, text=e, variable=self.etage_sel, value=e,
                           bg=BGUI, fg=WHITE, selectcolor=BG3, activebackground=BGUI,
                           font=("Consolas",9),
                           command=self._highlight).grid(row=i, column=0, sticky="w", padx=6, pady=1)

        # Lecteur
        tk.Label(mid, text="LECTEUR RC522", bg=BGUI, fg=GRIS,
                 font=("Consolas",9,"bold")).pack(pady=(14,3))
        self.reader_cv = tk.Canvas(mid, bg=BG2, width=150, height=110,
                                   highlightthickness=1, highlightbackground="#333")
        self.reader_cv.pack()
        self._draw_reader()

        self.status_var = tk.StringVar(value="En attente d'un badge...")
        self.status_lbl = tk.Label(mid, textvariable=self.status_var,
                                   bg=BGUI, fg=GRIS, font=("Consolas",9),
                                   wraplength=175, justify="center")
        self.status_lbl.pack(pady=5)

        self.led_cv = tk.Canvas(mid, bg=BGUI, width=80, height=26, highlightthickness=0)
        self.led_cv.pack()
        self.led_v = self.led_cv.create_oval(4,4,22,22,   fill="#333", outline="#555")
        self.led_r = self.led_cv.create_oval(58,4,76,22,  fill="#333", outline="#555")
        tk.Label(mid, text="Vert       Rouge", bg=BGUI, fg="#555",
                 font=("Consolas",8)).pack()

        # Badges
        tk.Label(mid, text="BADGES", bg=BGUI, fg=GRIS,
                 font=("Consolas",9,"bold")).pack(pady=(12,3))
        self.badge_btns = []
        for uid, info in DROITS.items():
            btn = tk.Button(mid, text=f"  {info['label']}\n  {uid}",
                            bg=info["color"], fg=WHITE, font=("Consolas",9,"bold"),
                            width=19, height=2, bd=0, cursor="hand2",
                            activebackground=info["color"],
                            command=lambda u=uid, i=info: self.scanner(u, i))
            btn.pack(pady=2)
            self.badge_btns.append(btn)

        self.panne_btn = tk.Button(mid, text="  Simuler panne réseau",
                                   bg="#555", fg=WHITE, font=("Consolas",9),
                                   width=19, bd=0, cursor="hand2",
                                   command=self.toggle_panne)
        self.panne_btn.pack(pady=(8,2))

        # Badges bloqués
        tk.Label(mid, text="BADGES BLOQUÉS", bg=BGUI, fg=ROUGE,
                 font=("Consolas",9,"bold")).pack(pady=(10,2))
        self.bloques_box = tk.Text(mid, bg=BG2, fg=ROUGE, font=("Consolas",9),
                                   width=22, height=4, bd=0, state="disabled")
        self.bloques_box.pack()

        # Colonne droite : logs
        right = tk.Frame(self.root, bg=BGUI)
        right.grid(row=2, column=2, padx=12, pady=4, sticky="n")

        tk.Label(right, text="FLUX TCP/IP + SÉCURITÉ", bg=BGUI, fg=GRIS,
                 font=("Consolas",9,"bold")).pack(anchor="w")
        self.tcp_box = tk.Text(right, bg=BG2, fg="#00ff88", font=("Consolas",9),
                               width=46, height=22, bd=0, state="disabled")
        self.tcp_box.pack(pady=(3,6))
        for tag, col in [("g",VERT),("r",ROUGE),("b","#64b5f6"),
                         ("y",JAUNE),("c",CYAN),("w",WHITE),("x",GRIS),
                         ("alerte","#FF5252"),("email","#FF9800")]:
            self.tcp_box.tag_config(tag, foreground=col)

        tk.Label(right, text="HISTORIQUE", bg=BGUI, fg=GRIS,
                 font=("Consolas",9,"bold")).pack(anchor="w")
        self.hist_box = tk.Text(right, bg=BG2, fg=GRIS, font=("Consolas",9),
                                width=46, height=9, bd=0, state="disabled")
        self.hist_box.pack(pady=(3,0))
        self.hist_box.tag_config("ok", foreground=VERT)
        self.hist_box.tag_config("ko", foreground=ROUGE)

        self._highlight()

    def _creer_batiment(self, parent, bat_id):
        cw, ch = 195, len(ETAGES)*44+30
        cv = tk.Canvas(parent, bg=BG2, width=cw, height=ch,
                       highlightthickness=1, highlightbackground="#333")
        cv.create_polygon(10,28,cw//2,4,cw-10,28, fill=BG3, outline="#aaa", width=1)
        cv.create_text(cw//2,16, text=f"Bât. {bat_id}",
                       fill=CYAN if bat_id=="A" else "#FF9800",
                       font=("Consolas",9,"bold"))
        for i, etage in enumerate(reversed(ETAGES)):
            y    = 30+i*44
            rect = cv.create_rectangle(10,y,cw-10,y+40, fill=BG3, outline="#555", width=1)
            lbl  = cv.create_text(cw//2,y+13, text=etage, fill=WHITE,
                                  font=("Consolas",8,"bold"))
            if etage=="RDC":
                cv.create_rectangle(cw//2-10,y+18,cw//2+10,y+40,
                                    fill="#333", outline="#888")
                cv.create_oval(cw//2+6,y+28,cw//2+9,y+31, fill=JAUNE, outline="")
            else:
                for wx in [cw//2-22, cw//2+8]:
                    cv.create_rectangle(wx,y+8,wx+16,y+26,
                                        fill="#1a3a5c", outline="#64b5f6", width=1)
                    cv.create_line(wx+8,y+8,wx+8,y+26, fill="#64b5f6", width=1)
                    cv.create_line(wx,y+17,wx+16,y+17, fill="#64b5f6", width=1)
            self.cellules[(bat_id,etage)] = (cv,rect,lbl)
        return cv

    def _draw_reader(self):
        cv=self.reader_cv; cx,cy=75,55
        for r,col in [(44,"#1a3a4a"),(32,"#1e4a5a"),(20,"#225a6a")]:
            cv.create_oval(cx-r,cy-r,cx+r,cy+r, outline=col, width=2, fill="")
        cv.create_rectangle(cx-14,cy-9,cx+14,cy+9,
                            fill="#0d2137", outline="#2196F3", width=2)
        cv.create_text(cx,cy, text="RC522", fill="#2196F3", font=("Consolas",8,"bold"))

    def _highlight(self):
        bat=self.bat_sel.get(); eta=self.etage_sel.get()
        for (b,e),(cv,rect,lbl) in self.cellules.items():
            if b==bat and e==eta:
                cv.itemconfig(rect, fill="#1F4E79", outline=CYAN, width=2)
                cv.itemconfig(lbl,  fill=CYAN)
            else:
                cv.itemconfig(rect, fill=BG3, outline="#555", width=1)
                cv.itemconfig(lbl,  fill=WHITE)

    # ── Scan ─────────────────────────────────────────────────
    def scanner(self, uid, info):
        if self.scanning: return
        self.scanning = True
        for b in self.badge_btns: b.config(state="disabled")
        threading.Thread(target=self._run_scan, args=(uid,info), daemon=True).start()

    def _run_scan(self, uid, info):
        global panne_reseau
        bat=self.bat_sel.get(); eta=self.etage_sel.get()
        label=info["label"]; color=info["color"]

        # Vérifier si badge bloqué
        bloque, restant = self.anomalies.est_bloque(uid)
        if bloque:
            self.log("─"*42, "x")
            self.log(f"[SÉCURITÉ] Badge {label} BLOQUÉ", "alerte")
            self.log(f"           Durée restante : {restant} min", "alerte")
            self.log(f"           Raison : trop de tentatives échouées", "alerte")
            self._set_status(f"🔒 BADGE BLOQUÉ\n{restant} min restantes", ROUGE)
            self._set_leds("rouge")
            self._flash(bat, eta, ROUGE)
            time.sleep(2)
            self._set_status("En attente d'un badge...", GRIS)
            self._set_leds("off")
            self._highlight()
            self._fin_scan(); return

        self._set_status("Lecture...", JAUNE)
        self._set_leds("off")
        self._flash(bat, eta, JAUNE)
        time.sleep(0.5)

        self.log("─"*42, "x")
        self.log(f"[ARDUINO]  {label} ({uid})", "w")
        self.log(f"           Bât.{bat}  |  {eta}", "c")
        self.log(f"           {datetime.now().strftime('%H:%M:%S')}", "x")
        time.sleep(0.3)

        if panne_reseau:
            self.log("\n[RÉSEAU]   ✘ TIMEOUT — fail-close → DENIED", "r")
            self._finaliser("DENIED", uid, bat, eta)
            self._fin_scan(); return

        # TCP handshake
        self.log("\n[TCP]  SYN ──► :5001", "b"); time.sleep(0.25)
        self.log("[TCP]  ◄── SYN-ACK", "b");    time.sleep(0.25)
        self.log("[TCP]  ACK ──► :5001", "b");   time.sleep(0.25)

        req = json.dumps({"type":"ACCESS_REQUEST","uid":uid,
                          "batiment":bat,"etage":eta,
                          "timestamp":datetime.now().strftime("%H:%M:%S")})
        self.log(f"\n[REQ]  {req}", "y"); time.sleep(0.4)

        try:
            sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((HOST, PORT))
            sock.sendall((req+"\n").encode())
            rep_str=sock.recv(1024).decode().strip()
            sock.close()
            rep=json.loads(rep_str)
            self.log(f"[REP]  {rep_str}", "y"); time.sleep(0.3)
            self.log("[TCP]  FIN / ACK", "b"); time.sleep(0.2)
            self._finaliser(rep.get("status","DENIED"), uid, bat, eta)
        except Exception as e:
            self.log(f"[ERR]  {e}", "r")
            self._finaliser("DENIED", uid, bat, eta)

        self._fin_scan()

    def _finaliser(self, statut, uid, bat, eta):
        # Enregistrer dans le gestionnaire d'anomalies
        self.anomalies.enregistrer(uid, statut, bat, eta)

        if statut=="GRANTED":
            self.log(f"\n[RÉSULTAT] ✔ ACCÈS ACCORDÉ — Bât.{bat} {eta}", "g")
            self._set_status(f"✔ ACCORDÉ\nBât.{bat} — {eta}", VERT)
            self._set_leds("vert")
            self._flash(bat, eta, VERT)
        else:
            self.log(f"\n[RÉSULTAT] ✘ ACCÈS REFUSÉ — Bât.{bat} {eta}", "r")
            self._set_status(f"✘ REFUSÉ\nBât.{bat} — {eta}", ROUGE)
            self._set_leds("rouge")
            self._flash(bat, eta, ROUGE)

        time.sleep(2)
        self._set_status("En attente d'un badge...", GRIS)
        self._set_leds("off")
        self._highlight()
        self._maj_hist()
        self._maj_bloques()

    def _on_anomalie(self, uid, evenement, details):
        """Callback du gestionnaire d'anomalies → mise à jour interface."""
        def _do():
            if evenement == "TENTATIVE":
                self.log(f"[ANOMALIE] {details}", "alerte")
            elif evenement == "ALERTE":
                self.log(f"\n{'!'*42}", "alerte")
                self.log(f"[ALERTE]   {details}", "alerte")
                self.log(f"[EMAIL]    Envoi alerte en cours...", "email")
                self.log(f"{'!'*42}\n", "alerte")
            elif evenement == "EMAIL_OK":
                self.log(f"[EMAIL]    ✔ {details}", "email")
            elif evenement == "EMAIL_ERR":
                self.log(f"[EMAIL]    ✘ Erreur : {details}", "r")
            self._maj_bloques()
        self.root.after(0, _do)

    def _flash(self, bat, eta, color, step=0):
        if step>5: self._highlight(); return
        key=(bat,eta)
        if key in self.cellules:
            cv,rect,lbl=self.cellules[key]
            fill=color if step%2==0 else BG3
            def _do(cv=cv,rect=rect,fill=fill,color=color,step=step):
                cv.itemconfig(rect,fill=fill,outline=color,width=2)
                self.root.after(280,lambda:self._flash(bat,eta,color,step+1))
            self.root.after(0,_do)

    def _fin_scan(self):
        self.scanning=False
        for b in self.badge_btns: b.config(state="normal")

    # ── Helpers ──────────────────────────────────────────────
    def log(self, msg, tag="w"):
        def _do():
            self.tcp_box.config(state="normal")
            self.tcp_box.insert("end", msg+"\n", tag)
            self.tcp_box.see("end")
            self.tcp_box.config(state="disabled")
        self.root.after(0,_do)

    def _set_status(self, msg, color):
        def _do():
            self.status_var.set(msg)
            self.status_lbl.config(fg=color)
        self.root.after(0,_do)

    def _set_leds(self, etat):
        def _do():
            self.led_cv.itemconfig(self.led_v, fill=VERT  if etat=="vert"  else "#333")
            self.led_cv.itemconfig(self.led_r, fill=ROUGE if etat=="rouge" else "#333")
        self.root.after(0,_do)

    def _maj_hist(self):
        def _do():
            self.hist_box.config(state="normal")
            self.hist_box.delete("1.0","end")
            for uid,bat,eta,st,ts in get_logs():
                tag="ok" if st=="GRANTED" else "ko"
                sym="✔" if st=="GRANTED" else "✘"
                self.hist_box.insert("end",
                    f" {sym} {ts}  {uid}  B.{bat}  {eta:<10}  {st}\n", tag)
            self.hist_box.config(state="disabled")
        self.root.after(0,_do)

    def _maj_bloques(self):
        def _do():
            bloques=self.anomalies.get_bloques()
            self.bloques_box.config(state="normal")
            self.bloques_box.delete("1.0","end")
            if not bloques:
                self.bloques_box.insert("end","  Aucun badge bloqué\n")
            for uid, restant in bloques:
                info=DROITS.get(uid,{})
                label=info.get("label",uid)
                self.bloques_box.insert("end",
                    f"  🔒 {label}\n     {restant} min restantes\n")
            self.bloques_box.config(state="disabled")
        self.root.after(0,_do)

    def toggle_panne(self):
        global panne_reseau
        panne_reseau=not panne_reseau
        if panne_reseau:
            self.panne_btn.config(text="  Rétablir le réseau", bg=ROUGE)
            self.log("\n[RÉSEAU]   ⚠ PANNE SIMULÉE", "r")
        else:
            self.panne_btn.config(text="  Simuler panne réseau", bg="#555")
            self.log("\n[RÉSEAU]   ✔ Réseau rétabli", "g")

# ============================================================
#  LANCEMENT
# ============================================================
if __name__ == "__main__":
    init_db()
    root=tk.Tk()
    root.geometry("1200x800")
    app=AppBatiment(root)
    root.mainloop()
    serveur_actif=False
