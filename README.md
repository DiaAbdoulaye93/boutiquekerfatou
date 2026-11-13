# Boutique vocale

Assistant multilingue (français, wolof, anglais, pulaar) d'une boutique de quartier sénégalaise. Le boutiquier pose sa question (« Quel est le produit le plus acheté ce mois-ci ? », « Ñaata la Modou Diop am bor ci man ? ») et reçoit une réponse courte, avec le détail à l'écran.

> **Toutes les données sont fictives.** La boutique « Keur Fatou », ses clients, ses produits et ses prix sont générés par `backend/app/seed/`. Aucun client ni aucune transaction réels.

## Fonctionnement

```
question ──► FastAPI /api/ask ──► Claude (outils, tool use strict)
                                     │  top_produits, chiffre_affaires, lister_factures,
                                     │  detail_facture, dettes_clients, situation_client,
                                     │  stock_bas, ventes_produit
                                     ▼
                              PostgreSQL (boutique fictive)
                                     │
réponse courte + langue ◄── outil « repondre »      cartes de résultats (mêmes données)
```

- Claude ne calcule rien : il choisit un outil, le backend interroge la base, et chaque chiffre prononcé vient d'un résultat d'outil. Les cartes affichées sont exactement ces résultats.
- La réponse finale est un appel à l'outil `repondre(texte, langue)`. La langue est donc structurée, prête pour la synthèse vocale.
- Les noms prononcés sont rapprochés du catalogue (accents, fautes de transcription, mots wolof comme *ceeb*, *suukar* ou *diwlin*).

## La voix

Un vocal passe par trois appels, pour que l'écran avance à chaque étape :

| Étape | Route | Moteur (via [Speko](https://speko.ai)) | Temps typique |
|---|---|---|---|
| Écoute | `POST /api/transcribe` | ElevenLabs Scribe, dans les trois langues | ~1,5 s |
| Réponse | `POST /api/ask` | Claude Opus 5.5 et les outils | ~5 à 7 s |
| Voix | `POST /api/speak` | Gemini 3.8 Flash-Lite TTS | ~2 à 4 s |

Le wolof, le français et l'anglais se parlent au micro ; la langue est choisie dans l'app avant de parler (Speko exige la langue pour transcrire). Le pulaar reste disponible à l'écrit.

Aucun moteur de synthèse n'accepte le code langue `wo` : le texte wolof est envoyé avec le code `fr`, et le modèle le lit tel qu'il est écrit. Ces choix viennent du banc d'essai de `bench/` (vocaux réels, taux d'erreur, compréhension de bout en bout, latence).

## Lancer en local

Prérequis : Python 3.12 avec [uv](https://docs.astral.sh/uv/), Node 24, PostgreSQL 16.

```bash
cd backend
cp .env.example .env          # renseigner ANTHROPIC_API_KEY et le mot de passe PostgreSQL
uv sync
uv run python scripts/seed.py # crée la boutique fictive (--reset pour la régénérer)
uv run uvicorn app.main:app --reload
```

```bash
cd frontend
npm ci
npm start                     # http://localhost:4200, /api redirigé vers :8000
```

Au démarrage, l'API génère la boutique si la base est vide, puis décale les dates par jours entiers pour que l'historique se termine aujourd'hui (`SLIDE_DATES_ON_STARTUP`). La démo n'a donc jamais l'air périmée.

## Tests

```bash
cd backend && uv run pytest -q          # Claude est remplacé par un faux client scripté
cd frontend && npm run lint && npm run build
```

## Déploiement : Render + Neon

1. **Neon** : créer un projet PostgreSQL (région Frankfurt, comme Render) et copier son URL de connexion *pooled* (`postgresql://…@ep-…-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require`). Les requêtes préparées sont désactivées côté app, le pooler de Neon fonctionne donc tel quel.
2. **Render** : *New > Blueprint*, choisir ce dépôt. `render.yaml` crée le service web (image Docker, contrôle `/health`) et demande quatre secrets :
   - `ANTHROPIC_API_KEY`
   - `SPEKO_API_KEY` : transcription et voix
   - `DATABASE_URL` : l'URL de Neon
   - `APP_PASSWORD` : obligatoire sur une URL publique, pour que personne ne consomme le budget Anthropic
3. Ensuite, chaque push sur `main` redéploie. La CI GitHub (`.github/workflows/ci.yml`) lance le lint et les tests.

Le premier démarrage remplit la base. Sur l'offre gratuite de Render, le service s'endort après 15 minutes sans visite : ouvrez l'app une minute avant de filmer.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ASSISTANT_MODEL` | `claude-opus-5-5` | modèle qui répond (`claude-haiku-5-5` : plus rapide, moins cher) |
| `ASSISTANT_EFFORT` | `low` | profondeur de réflexion |
| `SEED_ON_STARTUP` | `true` | génère la boutique si la base est vide |
| `SLIDE_DATES_ON_STARTUP` | `true` | fait finir l'historique aujourd'hui |
| `SHOP_NAME` | `Boutique Keur Fatou` | nom affiché |
| `APP_PASSWORD` | vide | mot de passe HTTP Basic sur toute l'app sauf `/health` et le manifeste PWA |
