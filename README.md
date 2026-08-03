# Database Fantacalcio

Archivio proprietario e multi-source dedicato ai calciatori e alle statistiche delle stagioni 2021-22, 2022-23, 2023-24, 2024-25 e 2025-26.

## Obiettivi

- PlayerID proprietario e permanente.
- Dati provenienti da fonti gratuite o autorizzate.
- Tracciabilità della fonte per ogni campo.
- Distinzione tra dati osservati, calcolati, stimati e manuali.
- Statistiche stagionali, partita per partita ed eventi spaziali.
- Infortuni, trasferimenti, premi, forma, rating, indici IA e similarità.
- Controlli automatici di qualità e deduplicazione.

## Fonti previste

- football-data.org
- API-Football
- StatsBomb Open Data
- TheSportsDB API v1

TheSportsDB usa la chiave gratuita pubblica `123`; football-data.org e API-Football richiedono chiavi personali, che non devono essere salvate nel repository.

## Sicurezza

Copia `.env.example` in `.env` e inserisci le chiavi solo nel file locale `.env`.

```bash
cp .env.example .env
```

Il file `.env` è escluso da Git tramite `.gitignore`.

## Inizializzazione

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pipeline.py --init
python pipeline.py --validate
```

## Regola fondamentale

Ogni valore deve essere classificato come:

- `observed`
- `calculated`
- `estimated`
- `manual`

Nessun dato mancante deve essere inventato. Ogni stima deve includere metodologia e confidence score.
