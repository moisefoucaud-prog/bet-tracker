# 🎯 Bet Tracker — Suivi de Paris Sportifs

Application web légère de suivi de paris sportifs avec réception automatique de signaux depuis le scanner.

## Installation

```bash
cd /root/workspace/background/bet-tracker
pip install -r requirements.txt
```

## Lancement

### Option 1 : Tracker seul (mode persistant)
```bash
cd /root/workspace/background/scanner-tracker-connect
./start_tracker.sh
```

### Option 2 : Tracker + Scanner (scan unique)
```bash
cd /root/workspace/background/scanner-tracker-connect
./start_all.sh
```

### Option 3 : Lancement manuel
```bash
# Terminal 1 : Tracker
cd /root/workspace/background/bet-tracker && python app.py

# Terminal 2 : Scanner (envoie automatiquement les signaux au tracker)
cd /root/workspace/background/signal-detector && python run_scanner.py
```

L'application sera accessible sur `http://localhost:5001`

## Connexion Scanner → Tracker

Le scanner (`run_scanner.py`) envoie automatiquement chaque signal détecté au tracker via `POST /api/signal`. 

- **Variable d'environnement** : `TRACKER_URL` (défaut: `http://localhost:5001`)
- **Robustesse** : si le tracker n'est pas disponible, le scanner continue sans planter
- **Log console** : `✅ Signal envoyé au tracker : [match]` ou `⚠️ Tracker non disponible`

## Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/` | Dashboard principal |
| GET | `/api/signals` | Liste des signaux en attente |
| POST | `/api/signal` | Ajouter un signal depuis le scanner |
| POST | `/api/bets` | Valider un signal en pari |
| GET | `/api/bets` | Liste des paris (filtrable) |
| PUT | `/api/bets/<id>/result` | Clôturer un pari (won/lost/void) |
| PUT | `/api/signals/<id>/ignore` | Ignorer un signal |
| GET | `/api/stats` | Statistiques globales |

## Envoi d'un signal depuis le scanner

```bash
curl -X POST http://localhost:5001/api/signal \
  -H "Content-Type: application/json" \
  -d '{
    "match": "Lyon vs Le Havre",
    "league": "Ligue 1",
    "date": "2026-08-30T15:00:00",
    "home_team": "Lyon",
    "away_team": "Le Havre",
    "odds": 1.51,
    "kelly_stake": 15.2,
    "filters": {
      "form": "4/5",
      "hst_ratio": "5.4 > 5.0",
      "odds_range": "1.40-1.60"
    }
  }'
```

## Stack technique

- **Backend**: Python Flask
- **Frontend**: HTML/CSS/JS + Chart.js (CDN)
- **Base de données**: SQLite (fichier `bets.db`)
- **Port**: 5001

## Design

- Dark theme professionnel
- Responsive (mobile-friendly)
- Bankroll initiale: 1000€
- Données de démonstration pré-chargées

## Scripts de démarrage

| Script | Description |
|--------|-------------|
| `start_all.sh` | Lance tracker + scanner, affiche URL dashboard |
| `start_tracker.sh` | Tracker seul en mode persistant (Ctrl+C pour arrêter) |
| `test_connection.py` | Vérifie la connexion scanner→tracker fonctionne |

Tous les scripts sont dans `/root/workspace/background/scanner-tracker-connect/`
