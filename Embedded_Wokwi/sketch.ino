/*
 * ============================================================
 *  Système de contrôle d'accès RFID — Partie 1
 *  Plateforme : Wokwi (board-mfrc522)
 *
 *  Cartes autorisées :
 *    - Bleue  (01020304) → GRANTED
 *    - Verte  (11223344) → GRANTED
 *  Carte refusée :
 *    - Rouge  (55667788) → DENIED
 * ============================================================
 */

#include <SPI.h>
#include <MFRC522.h>

#define PIN_SDA       10
#define PIN_RST        9
#define PIN_LED_VERT   7
#define PIN_LED_ROUGE  6
#define PIN_BUZZER     8

MFRC522 rfid(PIN_SDA, PIN_RST);

const String UIDS_AUTORISES[] = {
  "01020304",  // Carte bleue
  "11223344"   // Carte verte
};
const int NB_UIDS = sizeof(UIDS_AUTORISES) / sizeof(UIDS_AUTORISES[0]);

unsigned long dernierAcces = 0;
const unsigned long DELAI_ANTI_REBOND = 2000;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  pinMode(PIN_LED_VERT,  OUTPUT);
  pinMode(PIN_LED_ROUGE, OUTPUT);
  pinMode(PIN_BUZZER,    OUTPUT);

  digitalWrite(PIN_LED_VERT,  LOW);
  digitalWrite(PIN_LED_ROUGE, LOW);
  digitalWrite(PIN_BUZZER,    LOW);

  Serial.println("========================================");
  Serial.println(" Systeme RFID - Controle d acces");
  Serial.println(" Cartes autorisees : Bleue, Verte");
  Serial.println(" Carte refusee     : Rouge");
  Serial.println("========================================");
  Serial.println("En attente d un badge...");
}

void loop() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;

  unsigned long maintenant = millis();
  if (maintenant - dernierAcces < DELAI_ANTI_REBOND) return;
  dernierAcces = maintenant;

  String uid = lireUID();

  Serial.println("----------------------------------------");
  Serial.print("[SCAN] UID detecte : ");
  Serial.println(uid);
  Serial.print("[INFO] Timestamp   : ");
  Serial.println(maintenant);

  if (estAutorise(uid)) {
    accesAccorde(uid);
  } else {
    accesRefuse(uid);
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

String lireUID() {
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

bool estAutorise(String uid) {
  for (int i = 0; i < NB_UIDS; i++) {
    if (uid == UIDS_AUTORISES[i]) return true;
  }
  return false;
}

void accesAccorde(String uid) {
  Serial.println("[ACCES] GRANTED");
  Serial.print("[LOG]   UID=");
  Serial.print(uid);
  Serial.println(" | STATUT=GRANTED | ACTION=VERROU_OUVERT");
  Serial.println();

  digitalWrite(PIN_LED_VERT, HIGH);
  tone(PIN_BUZZER, 1000, 150);
  delay(2000);
  digitalWrite(PIN_LED_VERT, LOW);
}

void accesRefuse(String uid) {
  Serial.println("[ACCES] DENIED");
  Serial.print("[LOG]   UID=");
  Serial.print(uid);
  Serial.println(" | STATUT=DENIED | ACTION=ALERTE");
  Serial.println();

  digitalWrite(PIN_LED_ROUGE, HIGH);
  tone(PIN_BUZZER, 300, 100);
  delay(150);
  tone(PIN_BUZZER, 300, 100);
  delay(2000);
  digitalWrite(PIN_LED_ROUGE, LOW);
}
