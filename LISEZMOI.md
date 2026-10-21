# Offres Qualité · Montpellier

Site qui rassemble chaque jour les offres d'ingénieure qualité agroalimentaire, assistante / technicienne qualité et responsable qualité / QHSE autour de Montpellier (25 km), avec un tableau de suivi des candidatures.

## Utiliser en local
- `actualiser.bat` : récupère les offres (écrit `data/offres.json`).
- `lancer.bat` : ouvre le site sur http://localhost:8765.

## Sources
| Source | Mode |
|---|---|
| LinkedIn, HelloWork | automatique, sans clé |
| France Travail, Adzuna, Jooble | automatique, **clé gratuite** (voir ci-dessous) |
| Indeed, Welcome to the Jungle, APEC, Jooble… | bloquent les robots : boutons de recherche pré-remplie sur le site |

### Clés gratuites (facultatives, ajoutent beaucoup d'offres)
- France Travail : https://francetravail.io → créer un compte, une application, activer l'API « Offres d'emploi v2 ». Secrets GitHub : `FT_CLIENT_ID`, `FT_CLIENT_SECRET`.
- Adzuna : https://developer.adzuna.com → secrets `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.
- Jooble : https://jooble.org/api/about → secret `JOOBLE_KEY` (reprend beaucoup d'annonces Indeed).

## Mise en ligne (GitHub Pages)
1. Créer un dépôt GitHub, y pousser ce dossier (branche `main`).
2. Settings → Pages → Source : **GitHub Actions**.
3. Actions → « Mise à jour des offres » → Run workflow. Ensuite la mise à jour se fait seule tous les matins à 7h (heure de Paris).

## Réglages
`collecte/config.json` : requêtes, rayon, mots exigés / exclus dans les titres.

## Suivi
Enregistré dans le navigateur (localStorage). Boutons « Sauvegarde » / « Restaurer » pour changer d'appareil, et « Exporter Excel (CSV) ».
