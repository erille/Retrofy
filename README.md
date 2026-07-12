# Retrofy

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask 3.0](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Spotify optional](https://img.shields.io/badge/Spotify-optional-1DB954?logo=spotify&logoColor=white)](SPOTIFY_SETUP.md)
[![Website](https://img.shields.io/badge/Site-retrofy.info-6A5ACD)](https://www.retrofy.info)
[![Last commit](https://img.shields.io/github/last-commit/erille/Cursor-Retrofy)](https://github.com/erille/Cursor-Retrofy/commits/main)

Retrofy est une application Flask pour explorer, enrichir et administrer une collection de disques vinyles stockée dans une base SQLite existante. Elle propose une expérience de navigation proche d'une discothèque numérique: recherche, filtres par artiste/genre/année, fiches détaillées, inventaire exportable, pochettes d'albums et lecteur Spotify optionnel.

Site web: [www.retrofy.info](https://www.retrofy.info)

Le projet est prévu pour tourner simplement avec Docker sur le port `8888`, avec une base SQLite montée depuis l'hôte et un dossier persistant pour les images.

## Fonctionnalités

- Accueil avec une sélection aléatoire de 30 albums disposant d'une pochette.
- Recherche par texte, artiste, année et genre.
- Navigation latérale par artistes, genres et années avec compteurs.
- Page inventaire avec tri, filtres, pagination progressive et export `JSON` ou `CSV`.
- Fiches détaillées avec métadonnées du disque, notes, informations artiste et pochette.
- Récupération automatique de pochettes via MusicBrainz et Cover Art Archive.
- Téléversement manuel de pochettes après connexion administrateur.
- Edition contrôlée des champs principaux après connexion administrateur.
- Authentification administrateur avec mots de passe hachés en bcrypt.
- Lecteur Spotify intégré sur les albums trouvés, lorsque les identifiants API sont configurés.
- Favicon multi-plateforme servi depuis le volume d'images persistant.

## Stack

- Python `3.11`
- Flask `3.0`
- SQLite
- Jinja templates
- Docker et Docker Compose
- MusicBrainz / Cover Art Archive pour les pochettes
- Spotify Web API via `spotipy` pour l'intégration optionnelle

## Prérequis

- Docker et Docker Compose.
- Une base SQLite existante disponible sur l'hôte.
- Un dossier hôte persistant pour les pochettes et favicons.
- Optionnel: des identifiants Spotify Developer pour afficher le lecteur Spotify.

Par défaut, la configuration Docker attend:

```text
/srv/sqlite/ma_base.sqlite
/srv/retrofy_images/
```

## Démarrage rapide

1. Préparez la configuration:

```bash
cp env.example .env
python generate_password.py
```

2. Renseignez au minimum les secrets dans `.env`:

```env
SECRET_KEY=changez-moi-avec-une-valeur-longue-et-aleatoire
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=votre-hash-bcrypt
```

3. Lancez l'application:

```bash
docker compose up --build -d
```

4. Ouvrez l'application:

```text
http://localhost:8888
```

En production, vérifiez que les variables `SECRET_KEY`, `ADMIN_USERNAME` et `ADMIN_PASSWORD_HASH` sont injectées dans le conteneur au runtime. Si un secret manque hors Docker, l'application en génère un aléatoire et aucun mot de passe administrateur connu n'est utilisable. Docker Compose exige explicitement `SECRET_KEY` au démarrage.

## Configuration

| Variable | Défaut | Description |
| --- | --- | --- |
| `DB_PATH` | `/srv/sqlite/ma_base.sqlite` | Chemin vers la base SQLite. |
| `IMAGES_DIR` | `/data/images` dans Docker | Dossier de stockage des pochettes. |
| `SECRET_KEY` | obligatoire avec Docker Compose | Clé de session Flask, longue et aléatoire. |
| `ADMIN_USERNAME` | `admin` | Identifiant administrateur. |
| `ADMIN_PASSWORD_HASH` | vide | Hash bcrypt du mot de passe administrateur. |
| `SPOTIFY_CLIENT_ID` | vide | Client ID Spotify, optionnel. |
| `SPOTIFY_CLIENT_SECRET` | vide | Client Secret Spotify, optionnel. |

Le fichier `docker-compose.yml` monte:

```yaml
volumes:
  - /srv/sqlite:/srv/sqlite:Z
  - /srv/retrofy_images:/data/images:Z
```

La base doit être accessible en écriture si vous utilisez l'édition des fiches depuis l'interface administrateur.

## Base de données attendue

Retrofy lit principalement les tables suivantes:

- `records`: catalogue principal des disques.
- `record_images`: association entre un disque et une image de pochette.
- `artistes`: informations complémentaires d'artiste, notamment le texte `a_propos`.

Les champs utilisés dans `records` incluent notamment `id`, `artist`, `album_title`, `year`, `label`, `catalog_number`, `format`, `country`, `barcode`, `matrix_runout`, `genre`, `style`, `media_condition`, `sleeve_condition`, `location`, `quantity`, `notes`, `price`, `currency`, `source`, `acquired_date`, `purchase_price`, `created_at`, `updated_at`, `artiste_id`, `storage` et `discogsid`.

## Administration

La connexion administrateur se fait depuis `/login`.

Une fois connecté, l'administrateur peut:

- téléverser une pochette;
- demander une recherche automatique de pochette;
- modifier certains champs d'une fiche disque.

Les champs éditables sont volontairement limités par liste blanche côté serveur afin d'éviter l'injection de noms de colonnes dans les requêtes SQL.

## Spotify

L'intégration Spotify est optionnelle. Lorsque `SPOTIFY_CLIENT_ID` et `SPOTIFY_CLIENT_SECRET` sont configurés, Retrofy recherche automatiquement l'album affiché sur Spotify et ajoute un lecteur intégré si une correspondance est trouvée.

Voir [SPOTIFY_SETUP.md](SPOTIFY_SETUP.md) pour le guide complet.

## Pochettes et favicons

Les pochettes sont servies via:

```text
/covers/<filename>
```

Les favicons sont servis via:

```text
/favicon/<filename>
```

Placez les fichiers favicon dans le dossier monté vers `/data/images`, par exemple `/srv/retrofy_images` sur l'hôte:

- `favicon.ico`
- `favicon-16x16.png`
- `favicon-32x32.png`
- `apple-touch-icon.png`
- `android-chrome-192x192.png`
- `android-chrome-512x512.png`

## Exports

La page inventaire permet d'exporter les résultats filtrés en:

- `JSON`
- `CSV`

Les exports sont aussi accessibles depuis `/export?format=json` ou `/export?format=csv`, avec les mêmes paramètres de filtre que l'inventaire.

## Scripts de vérification

Le dépôt contient plusieurs scripts de vérification autonomes:

```bash
python test_security.py
python test_sql_injection_fix.py
python test_random_covers.py
python test_spotify_integration.py
python test_favicon.py
python test_favicon_access.py
```

Ces scripts ne constituent pas une suite `pytest` complète; ils valident des points ciblés comme le hachage bcrypt, la protection SQL, les pochettes aléatoires, l'intégration Spotify et les favicons.

## Structure du projet

```text
.
├── app.py                  # Application Flask et routes
├── templates/              # Pages Jinja
├── static/styles.css       # Styles de l'interface
├── Dockerfile              # Image Python Flask
├── docker-compose.yml      # Déploiement local/serveur
├── env.example             # Exemple de configuration
├── generate_password.py    # Générateur de hash bcrypt
├── SPOTIFY_SETUP.md        # Guide Spotify
└── test_*.py               # Scripts de vérification
```

## Sécurité

- Ne gardez jamais le mot de passe par défaut en production.
- Utilisez une valeur longue et aléatoire pour `SECRET_KEY`.
- Injectez les secrets au runtime plutôt que de les commiter dans le dépôt.
- Gardez le volume SQLite protégé: il contient les données éditées depuis l'interface.
- L'upload de pochettes est réservé aux sessions administrateur.

## Licence

Aucune licence n'est actuellement déclarée dans le dépôt. Ajoutez un fichier `LICENSE` si vous souhaitez préciser les conditions d'utilisation ou de contribution.
