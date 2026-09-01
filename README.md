# RFID-Access-Control-TCP-IP

## Project Overview

This project presents the design and simulation of a complete **RFID-based access control system** communicating over a **TCP/IP network**.

The system combines an embedded RFID reader, a Python gateway, a central TCP server, SQLite databases, and a graphical network simulation. The main objective is to simulate how an RFID access control infrastructure can identify users, communicate with a central server, make access decisions, and record access events.

---

## Objectives

The main objectives of the project were to:

* Design an RFID-based access control architecture.
* Simulate an Arduino + RC522 RFID reader using Wokwi.
* Develop a Python gateway for communication between the embedded system and the network.
* Design and implement an application-level protocol using **JSON over TCP/IP**.
* Develop a central Python TCP server.
* Store authorized badges and access logs using **SQLite**.
* Simulate network communication and access scenarios using Python and Tkinter.
* Implement a **fail-close security policy**, where access is denied in case of communication or processing errors.
* Test the system using authorized badges, unknown badges, and network failure scenarios.

---

## System Architecture

The system is organized into several communicating layers:

```text
                    RFID BADGE
                        │
                        ▼
              ┌───────────────────┐
              │ Arduino + RC522   │
              │      Wokwi        │
              └─────────┬─────────┘
                        │
                     Serial
                        │
                        ▼
              ┌───────────────────┐
              │  Python Gateway  │
              │  passerelle.py   │
              └─────────┬─────────┘
                        │
                    TCP + JSON
                        │
                        ▼
              ┌───────────────────┐
              │   TCP Server      │
              │   serveur.py      │
              │                   │
              │     SQLite        │
              └─────────┬─────────┘
                        │
                 GRANTED / DENIED
                        │
                        ▼
              ┌───────────────────┐
              │ Access Decision   │
              │ LED / Buzzer      │
              └───────────────────┘
```

---

## Technologies

* **Arduino / C++**
* **RFID**
* **MFRC522 / RC522**
* **Wokwi**
* **Python**
* **TCP/IP**
* **JSON**
* **Socket programming**
* **SQLite**
* **Tkinter**
* **Multithreading**

---


