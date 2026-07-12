import os
import secrets
import sqlite3
import csv
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
import json
import requests
import bcrypt
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Load environment variables
load_dotenv()


# Configuration
DB_PATH = os.environ.get("DB_PATH", "/srv/sqlite/ma_base.sqlite")
IMAGES_DIR = os.environ.get("IMAGES_DIR", os.path.join(os.getcwd(), "images"))
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
SQL_WHERE = " WHERE "
SQL_AND = " AND "
INVENTORY_COLUMNS = (
    "id", "artist", "album_title", "year", "label", "catalog_number",
    "format", "country", "notes", "price", "currency",
)
INVENTORY_SELECT = ", ".join(INVENTORY_COLUMNS)
INVENTORY_ORDER_EXPRESSION = """CASE ?
    WHEN 'id' THEN id
    WHEN 'artist' THEN artist
    WHEN 'album_title' THEN album_title
    WHEN 'year' THEN year
    WHEN 'label' THEN label
    WHEN 'catalog_number' THEN catalog_number
    WHEN 'format' THEN format
    WHEN 'country' THEN country
    WHEN 'notes' THEN notes
    WHEN 'price' THEN price
    WHEN 'currency' THEN currency
    ELSE id END"""
INVENTORY_ORDER_ASC = f" ORDER BY {INVENTORY_ORDER_EXPRESSION} ASC LIMIT ? OFFSET ?"
INVENTORY_ORDER_DESC = f" ORDER BY {INVENTORY_ORDER_EXPRESSION} DESC LIMIT ? OFFSET ?"
INVENTORY_FILTER_COLUMNS = {
    "artist_filter": "artist",
    "album_filter": "album_title",
    "year_filter": "year",
    "label_filter": "label",
    "catalog_filter": "catalog_number",
}
EXPORT_FIELDS = (
    "id", "artist", "album_title", "year", "label", "catalog_number", "format", "country",
    "barcode", "matrix_runout", "genre", "style", "media_condition", "sleeve_condition",
    "location", "quantity", "notes", "price", "currency", "source", "acquired_date",
    "purchase_price", "created_at", "updated_at", "artiste_id", "storage", "discogsid",
)
EXPORT_HEADERS = (
    "ID", "Artiste", "Album", "Année", "Label", "N° Catalogue", "Format", "Pays",
    "Code-barres", "Matrix/Runout", "Genre", "Style", "État Media", "État Pochette",
    "Localisation", "Quantité", "Notes", "Prix", "Devise", "Source", "Date Acquisition",
    "Prix Achat", "Date Création", "Date Modification", "ID Artiste", "Stockage", "Discogs ID",
)

# User authentication configuration
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

# Generate a random development credential if none is provided. Production must
# always inject ADMIN_PASSWORD_HASH; no known fallback password is created.
if not ADMIN_PASSWORD_HASH:
    ADMIN_PASSWORD_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode("utf-8")

# Spotify configuration
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def ensure_directories() -> None:
    os.makedirs(IMAGES_DIR, exist_ok=True)


def create_app() -> Flask:
    ensure_directories()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=SECRET_KEY,
        DB_PATH=DB_PATH,
        IMAGES_DIR=IMAGES_DIR,
    )

    @app.before_request
    def before_request() -> None:
        g.db = get_db_connection()

    @app.teardown_request
    def teardown_request(exception: Optional[BaseException]) -> None:  # noqa: U100
        db = getattr(g, "db", None)
        if db is not None:
            db.close()

    CSRFProtect(app)
    register_routes(app)
    return app


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query_records(
    db: sqlite3.Connection,
    q: Optional[str] = None,
    artist: Optional[str] = None,
    year: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = 100,
) -> List[sqlite3.Row]:
    sql = "SELECT * FROM records"
    clauses: List[str] = []
    params: List[Any] = []

    if q:
        like = f"%{q}%"
        clauses.append(
            "(artist LIKE ? OR album_title LIKE ? OR label LIKE ? OR genre LIKE ? OR style LIKE ? OR notes LIKE ?)"
        )
        params.extend([like, like, like, like, like, like])
    if artist:
        clauses.append("artist LIKE ?")
        params.append(f"%{artist}%")
    if year:
        clauses.append("year = ?")
        params.append(year)
    if genre:
        clauses.append("genre LIKE ?")
        params.append(f"%{genre}%")

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY artist, year, album_title"
    sql += " LIMIT ?"
    params.append(limit)

    cur = db.execute(sql, params)
    return cur.fetchall()


def get_record(db: sqlite3.Connection, record_id: int) -> sqlite3.Row:
    cur = db.execute("SELECT * FROM records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    if not row:
        abort(404)
    return row


def get_artist_info(db: sqlite3.Connection, artist_id: int) -> Optional[sqlite3.Row]:
    if not artist_id:
        return None
    cur = db.execute("SELECT * FROM artistes WHERE id = ?", (artist_id,))
    return cur.fetchone()


def get_record_image(db: sqlite3.Connection, record_id: int) -> Optional[sqlite3.Row]:
    cur = db.execute(
        "SELECT * FROM record_images WHERE record_id = ? ORDER BY id DESC LIMIT 1",
        (record_id,),
    )
    return cur.fetchone()


def save_record_image(
    db: sqlite3.Connection, record_id: int, filename: str, kind: str = "cover", note: Optional[str] = None
) -> None:
    db.execute(
        "INSERT INTO record_images (record_id, kind, filename, note) VALUES (?, ?, ?, ?)",
        (record_id, kind, filename, note),
    )
    db.commit()


def get_artists_with_counts(db: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = db.execute(
        """
        SELECT artist, COUNT(*) AS num_records
        FROM records
        WHERE artist IS NOT NULL AND TRIM(artist) <> ''
        GROUP BY artist
        ORDER BY num_records DESC, LOWER(artist) ASC
        """
    )
    return cur.fetchall()


def get_genres_with_counts(db: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = db.execute(
        """
        SELECT genre, COUNT(*) AS num_records
        FROM records
        WHERE genre IS NOT NULL AND TRIM(genre) <> ''
        GROUP BY genre
        ORDER BY num_records DESC, LOWER(genre) ASC
        """
    )
    return cur.fetchall()


def get_years_with_counts(db: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = db.execute(
        """
        SELECT year, COUNT(*) AS num_records
        FROM records
        WHERE year IS NOT NULL AND TRIM(CAST(year AS TEXT)) <> ''
        GROUP BY year
        ORDER BY year DESC
        """
    )
    return cur.fetchall()


def get_latest_records(db: sqlite3.Connection, limit: int = 8) -> List[sqlite3.Row]:
    cur = db.execute(
        """
        SELECT * FROM records
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,)
    )
    return cur.fetchall()


def get_random_records_with_covers(db: sqlite3.Connection, limit: int = 30) -> Tuple[List[sqlite3.Row], Dict[int, str]]:
    """Get random records that have cover images (not default.jpg) and return both records and image filenames."""
    cur = db.execute(
        """
        SELECT DISTINCT r.*, ri.filename as cover_filename
        FROM records r
        INNER JOIN record_images ri ON r.id = ri.record_id
        WHERE ri.filename IS NOT NULL 
        AND ri.filename != 'default.jpg'
        AND ri.filename NOT LIKE '%default%'
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    
    # Extract records and create images map
    records = []
    images_map = {}
    for row in rows:
        record_dict = dict(row)
        cover_filename = record_dict.pop('cover_filename', None)
        records.append(type('Record', (), record_dict)())  # Convert back to Row-like object
        images_map[record_dict['id']] = cover_filename
    
    return records, images_map


def get_records_count(db: sqlite3.Connection) -> int:
    """Get the total number of records in the database."""
    cur = db.execute("SELECT COUNT(*) as count FROM records")
    result = cur.fetchone()
    return result["count"] if result else 0


def fetch_cover_via_musicbrainz(artist: str, album_title: str) -> Optional[Tuple[str, bytes]]:
    # Try MusicBrainz release-group lookup first
    base = "https://musicbrainz.org/ws/2"
    headers = {"User-Agent": "Retrofy/1.0 (retrofy.local)"}
    q = f"artist:{artist} AND releasegroup:{album_title}"
    try:
        rg_resp = requests.get(
            f"{base}/release-group",
            params={"query": q, "fmt": "json"},
            headers=headers,
            timeout=10,
        )
        rg_resp.raise_for_status()
        data = rg_resp.json()
        groups = data.get("release-groups", [])
        if groups:
            mbid = groups[0]["id"]
            img = fetch_caa_image("release-group", mbid)
            if img:
                return (f"mb_rg_{mbid}.jpg", img)
    except Exception:  # noqa: BLE001
        pass

    # Fallback to release search
    try:
        r_resp = requests.get(
            f"{base}/release",
            params={"query": f"artist:{artist} AND release:{album_title}", "fmt": "json"},
            headers=headers,
            timeout=10,
        )
        r_resp.raise_for_status()
        data = r_resp.json()
        releases = data.get("releases", [])
        if releases:
            mbid = releases[0]["id"]
            img = fetch_caa_image("release", mbid)
            if img:
                return (f"mb_rel_{mbid}.jpg", img)
    except Exception:  # noqa: BLE001
        pass

    return None


def fetch_caa_image(kind: str, mbid: str) -> Optional[bytes]:
    url = f"https://coverartarchive.org/{kind}/{mbid}/front"
    headers = {"User-Agent": "Retrofy/1.0 (retrofy.local)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:  # noqa: BLE001
        return None
    return None


def save_image_bytes(content: bytes, suggested_name: str, record_id: int) -> str:
    extension = os.path.splitext(suggested_name)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        extension = ".jpg"
    safe_name = f"record_{record_id}_{secrets.token_hex(16)}{extension}"
    images_root = os.path.realpath(IMAGES_DIR)
    path = os.path.realpath(os.path.join(images_root, safe_name))
    if os.path.commonpath((images_root, path)) != images_root:
        raise ValueError("Invalid image path")
    with open(path, "wb") as f:
        f.write(content)
    return safe_name


def get_inventory_filters() -> Dict[str, str]:
    return {name: request.args.get(name, "") for name in INVENTORY_FILTER_COLUMNS}


def build_filter_clause(filters: Dict[str, str]) -> Tuple[str, List[str]]:
    clauses = []
    params = []
    for name, column in INVENTORY_FILTER_COLUMNS.items():
        if filters[name]:
            clauses.append(f"{column} LIKE ?")
            params.append(f"%{filters[name]}%")
    where_clause = SQL_WHERE + SQL_AND.join(clauses) if clauses else ""
    return where_clause, params


def inventory_sort() -> Tuple[str, str, str]:
    sort_by = request.args.get("sort", "id")
    if sort_by not in INVENTORY_COLUMNS:
        sort_by = "id"
    requested_order = request.args.get("order", "asc").lower()
    direction = "ASC" if requested_order == "asc" else "DESC"
    return sort_by, requested_order, direction


def fetch_inventory_page(db: sqlite3.Connection, page: int, per_page: int) -> Tuple[List[sqlite3.Row], int]:
    filters = get_inventory_filters()
    where_clause, params = build_filter_clause(filters)
    total = db.execute("SELECT COUNT(*) AS total FROM records" + where_clause, params).fetchone()["total"]
    sort_by, _, direction = inventory_sort()
    order_clause = INVENTORY_ORDER_ASC if direction == "ASC" else INVENTORY_ORDER_DESC
    sql = "SELECT " + INVENTORY_SELECT + " FROM records" + where_clause + order_clause
    rows = db.execute(sql, [*params, sort_by, per_page, (page - 1) * per_page]).fetchall()
    return rows, total


def json_export_response(records: List[sqlite3.Row]):
    payload = [{field: record[field] for field in EXPORT_FIELDS} for record in records]
    response = make_response(json.dumps(payload, ensure_ascii=False, indent=2))
    response.headers["Content-Type"] = "application/json"
    response.headers["Content-Disposition"] = "attachment; filename=retrofy_records.json"
    return response


def csv_export_response(records: List[sqlite3.Row]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPORT_HEADERS)
    writer.writerows([[record[field] or "" for field in EXPORT_FIELDS] for record in records])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=retrofy_records.csv"
    return response


def get_index_records(db: sqlite3.Connection, filters: Dict[str, Optional[str]]):
    has_filters = any(filters.values())
    if not has_filters:
        records, images = get_random_records_with_covers(db, limit=30)
        return records, images, False
    records = query_records(db, **filters)
    images = {}
    for record in records:
        image = get_record_image(db, record["id"])
        images[record["id"]] = image["filename"] if image else None
    return records, images, True


def search_spotify_album(artist: str, album_title: str) -> Optional[Dict[str, Any]]:
    """Search for an album on Spotify and return its information."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    
    try:
        # Initialize Spotify client
        client_credentials_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
        
        # Search for the album
        query = f"artist:{artist} album:{album_title}"
        results = sp.search(q=query, type='album', limit=1)
        
        if results['albums']['items']:
            album = results['albums']['items'][0]
            return {
                'id': album['id'],
                'name': album['name'],
                'artist': album['artists'][0]['name'] if album['artists'] else '',
                'external_url': album['external_urls']['spotify'],
                'images': album['images']
            }
    except Exception as e:
        # Log error but don't crash the application
        print(f"Spotify search error: {e}")
        return None
    
    return None


def is_logged_in() -> bool:
    return session.get("user") == ADMIN_USERNAME


def login_required() -> None:
    if not is_logged_in():
        abort(403)


def register_sidebar_context(app: Flask) -> None:
    @app.context_processor
    def inject_sidebar_data():
        try:
            artists = get_artists_with_counts(g.db)
            genres = get_genres_with_counts(g.db)
            years = get_years_with_counts(g.db)
        except Exception:  # noqa: BLE001
            artists = []
            genres = []
            years = []
        return {"artist_counts": artists, "genre_counts": genres, "year_counts": years}

def register_core_routes(app: Flask) -> None:
    @app.get("/a-propos")
    def a_propos():
        return render_template("a_propos.html")

    @app.get("/")
    def index():
        filters = {name: request.args.get(name) for name in ("q", "artist", "year", "genre")}
        records, images_map, has_filters = get_index_records(g.db, filters)
        records_count = get_records_count(g.db) if not has_filters else 0

        return render_template(
            "index.html",
            records=records,
            images_map=images_map,
            **{name: value or "" for name, value in filters.items()},
            is_welcome=not has_filters,
            records_count=records_count,
        )

def register_inventory_page(app: Flask) -> None:
    @app.get("/inventaire")
    def inventaire():
        sort_by, sort_order, _ = inventory_sort()
        filters = get_inventory_filters()
        page = max(request.args.get("page", 1, type=int), 1)
        per_page = 100
        records, total_records = fetch_inventory_page(g.db, page, per_page)
        total_pages = (total_records + per_page - 1) // per_page
        
        return render_template(
            "inventaire.html",
            records=records,
            sort_by=sort_by,
            sort_order=sort_order,
            **filters,
            current_page=page,
            total_pages=total_pages,
            total_records=total_records,
            per_page=per_page,
        )

def register_export_route(app: Flask) -> None:
    @app.get("/export")
    def export_records():
        format_type = request.args.get("format", "json")
        where_clause, params = build_filter_clause(get_inventory_filters())
        sql = "SELECT * FROM records" + where_clause + " ORDER BY id ASC"

        cursor = g.db.execute(sql, params)
        records = cursor.fetchall()

        if format_type == "json":
            return json_export_response(records)
        
        if format_type == "csv":
            return csv_export_response(records)
        
        else:
            abort(400, "Format non supporté. Utilisez 'json' ou 'csv'.")

def register_inventory_api(app: Flask) -> None:
    @app.get("/api/inventaire")
    def api_inventaire():
        page = max(request.args.get("page", 1, type=int), 1)
        per_page = 100
        records, _ = fetch_inventory_page(g.db, page, per_page)
        
        # Convert to list of dictionaries
        records_list = []
        for record in records:
            records_list.append({
                'id': record['id'],
                'artist': record['artist'] or '',
                'album_title': record['album_title'] or '',
                'year': record['year'] or '',
                'label': record['label'] or '',
                'catalog_number': record['catalog_number'] or '',
                'format': record['format'] or '',
                'country': record['country'] or '',
                'notes': record['notes'] or '',
                'price': record['price'] or '',
                'currency': record['currency'] or ''
            })
        
        # Debug logging
        print(f"API call - Page: {page}, Records returned: {len(records_list)}, Has more: {len(records_list) == per_page}")
        
        return jsonify({
            'records': records_list,
            'page': page,
            'has_more': len(records_list) == per_page
        })

def register_record_routes(app: Flask) -> None:
    @app.get("/records/<int:record_id>")
    def record_detail(record_id: int):
        rec = get_record(g.db, record_id)
        img = get_record_image(g.db, record_id)
        artist = get_artist_info(g.db, rec["artiste_id"]) if rec["artiste_id"] else None
        
        # Search for album on Spotify
        spotify_album = search_spotify_album(rec["artist"], rec["album_title"])
        
        return render_template("detail.html", record=rec, image=img, artist=artist, spotify_album=spotify_album)

    @app.post("/records/<int:record_id>/fetch_cover")
    def record_fetch_cover(record_id: int):
        rec = get_record(g.db, record_id)
        if get_record_image(g.db, record_id):
            return redirect(url_for("record_detail", record_id=record_id))
        found = fetch_cover_via_musicbrainz(rec["artist"], rec["album_title"])  # type: ignore[index]
        if found:
            filename, content = found
            saved = save_image_bytes(content, filename, record_id)
            save_record_image(g.db, record_id, saved, kind="cover", note="auto-fetched")
            flash("Pochette ajoutée automatiquement.", "success")
        else:
            flash("Pochette introuvable.", "warning")
        return redirect(url_for("record_detail", record_id=record_id))

    @app.post("/records/<int:record_id>/upload_cover")
    def upload_cover(record_id: int):
        login_required()
        if "cover" not in request.files:
            flash("Fichier manquant.", "error")
            return redirect(url_for("record_detail", record_id=record_id))
        f = request.files["cover"]
        if not f.filename:
            flash("Nom de fichier invalide.", "error")
            return redirect(url_for("record_detail", record_id=record_id))
        content = f.read()
        saved = save_image_bytes(content, f.filename, record_id)
        save_record_image(g.db, record_id, saved, kind="cover", note="uploaded")
        flash("Pochette importée.", "success")
        return redirect(url_for("record_detail", record_id=record_id))

    @app.get("/covers/<path:filename>")
    def serve_cover(filename: str):
        return send_from_directory(IMAGES_DIR, filename)

    @app.get("/favicon/<path:filename>")
    def serve_favicon(filename: str):
        """Serve favicon files from the retrofy_images directory."""
        favicon_dir = "/data/images"  # This is the mounted directory in the container
        return send_from_directory(favicon_dir, filename)

def register_auth_routes(app: Flask) -> None:
    @app.get("/login")
    def login_form():
        return render_template("login.html")

    @app.post("/login")
    def login_post():
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        
        # Check username and password
        if (username == ADMIN_USERNAME and 
            bcrypt.checkpw(password.encode('utf-8'), ADMIN_PASSWORD_HASH.encode('utf-8'))):
            session["user"] = ADMIN_USERNAME
            flash("Connecté.", "success")
            return redirect(url_for("index"))
        
        flash("Identifiants invalides.", "error")
        return redirect(url_for("login_form"))

    @app.post("/logout")
    def logout():
        session.pop("user", None)
        flash("Déconnecté.", "success")
        return redirect(url_for("index"))

def register_edit_route(app: Flask) -> None:
    @app.post("/records/<int:record_id>/edit")
    def edit_record(record_id: int):
        login_required()
        rec = get_record(g.db, record_id)
        
        # Define allowed fields with explicit whitelist to prevent SQL injection
        ALLOWED_FIELDS = {
            "artist": "artist",
            "album_title": "album_title", 
            "year": "year",
            "label": "label",
            "genre": "genre",
            "style": "style",
            "location": "location",
            "notes": "notes",
            "price": "price",
            "currency": "currency",
            "quantity": "quantity",
        }
        
        # Build update clauses safely using whitelisted field names
        update_clauses: List[str] = []
        values: List[Any] = []
        
        for form_field, db_column in ALLOWED_FIELDS.items():
            if form_field in request.form:
                # Only add valid, whitelisted fields to prevent SQL injection
                update_clauses.append(f"{db_column} = ?")
                values.append(request.form.get(form_field))
        
        if update_clauses:
            # Construct the SQL query with whitelisted field names
            sql = "UPDATE records SET " + ", ".join(update_clauses) + ", updated_at = datetime('now') WHERE id = ?"
            values.append(record_id)
            
            try:
                g.db.execute(sql, tuple(values))
                g.db.commit()
                flash("Enregistrement mis à jour.", "success")
            except sqlite3.Error as e:
                g.db.rollback()
                flash(f"Erreur lors de la mise à jour: {str(e)}", "error")
        else:
            flash("Aucun changement détecté.", "warning")
            
        return redirect(url_for("record_detail", record_id=rec["id"]))  # type: ignore[index]


def register_routes(app: Flask) -> None:
    register_sidebar_context(app)
    register_core_routes(app)
    register_inventory_page(app)
    register_export_route(app)
    register_inventory_api(app)
    register_record_routes(app)
    register_auth_routes(app)
    register_edit_route(app)


app = create_app()


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=8888, debug=False)
