import os, sqlite3, threading, exifread, time, schedule, io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import ssl
import certifi
import geopy.geocoders
from geopy.geocoders import Nominatim


app = Flask(__name__)
# Ensure the DB is stored in the same folder as the script
DB_PATH = os.path.join(os.path.dirname(__file__), 'photos.db')

# Global state to prevent concurrent scans
is_scanning = False
# This tells geopy exactly where to find the trusted certificates
ctx = ssl.create_default_context(cafile=certifi.where())
geolocator = Nominatim(
    user_agent="syno_mapper_v1", 
    ssl_context=ctx
)
# --- DATABASE HELPERS ---

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            pic_local_path TEXT UNIQUE, 
            gps_position TEXT, 
            city TEXT, department TEXT, region TEXT, country TEXT
        )''')
        conn.execute('CREATE TABLE IF NOT EXISTS scan_paths (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE)')
        conn.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, scan_interval_hours INTEGER DEFAULT 24, last_run TEXT)')
        conn.execute("INSERT OR IGNORE INTO settings (id, scan_interval_hours) VALUES (1, 24)")
        conn.commit()

# --- GPS EXTRACTION ---

def convert_to_degrees(value):
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)

def extract_gps(path):
    try:
        with open(path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            lat_ref = tags.get('GPS GPSLatitudeRef')
            lat = tags.get('GPS GPSLatitude')
            lon_ref = tags.get('GPS GPSLongitudeRef')
            lon = tags.get('GPS GPSLongitude')
            if lat and lat_ref and lon and lon_ref:
                lat_val = convert_to_degrees(lat)
                if lat_ref.values[0] != 'N': lat_val = -lat_val
                lon_val = convert_to_degrees(lon)
                if lon_ref.values[0] != 'E': lon_val = -lon_val
                return f"{lat_val},{lon_val}"
    except: pass
    return None

# --- CORE SCANNING LOGIC ---

def scan_photos():
    global is_scanning
    if is_scanning: return
    is_scanning = True
    print(f"[{datetime.now()}] Scan started...")
    
    conn = get_db_connection()
    paths = [row['path'] for row in conn.execute("SELECT path FROM scan_paths").fetchall()]
    
    for base_path in paths:
        if not os.path.exists(base_path): continue
        for root, _, files in os.walk(base_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg')):
                    full_path = os.path.join(root, file)
                    if conn.execute("SELECT 1 FROM photos WHERE pic_local_path=?", (full_path,)).fetchone():
                        continue
                    
                    gps = extract_gps(full_path)
                    if gps:
                        try:
                            loc = geolocator.reverse(gps, language='en', timeout=10)
                            addr = loc.raw.get('address', {})
                            conn.execute("""INSERT INTO photos (pic_local_path, gps_position, city, department, region, country) 
                                            VALUES (?,?,?,?,?,?)""",
                                (full_path, gps, 
                                 addr.get('city') or addr.get('town') or addr.get('village'), 
                                 addr.get('county'), addr.get('state'), addr.get('country')))
                            conn.commit()
                            time.sleep(1.1) # Respect Nominatim usage policy
                        except Exception as e:
                            print(f"Geocoding error for {full_path}: {e}")
    
    conn.execute("UPDATE settings SET last_run = ? WHERE id = 1", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()
    is_scanning = False
    print(f"[{datetime.now()}] Scan finished.")

# --- BACKGROUND SCHEDULER ---

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

# --- FLASK ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    visited_countries = [row['country'] for row in conn.execute("SELECT DISTINCT country FROM photos WHERE country IS NOT NULL").fetchall()]

    results = []
    query = request.form.get('query', '')
    
    if query:
        lq = f"%{query}%"
        results = conn.execute("""SELECT * FROM photos WHERE city LIKE ? OR department LIKE ? 
                                  OR region LIKE ? OR country LIKE ?""", (lq, lq, lq, lq)).fetchall()
    
    conn.close()
    return render_template('index.html', results=results, query=query, visited_countries=visited_countries)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    conn = get_db_connection()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            path = request.form.get('new_path')
            if path: conn.execute("INSERT OR IGNORE INTO scan_paths (path) VALUES (?)", (path,))
        elif action == 'delete':
            conn.execute("DELETE FROM scan_paths WHERE id = ?", (request.form.get('path_id'),))
        elif action == 'update_interval':
            hrs = int(request.form.get('interval', 24))
            conn.execute("UPDATE settings SET scan_interval_hours = ? WHERE id = 1", (hrs,))
            schedule.clear('daily_scan')
            schedule.every(hrs).hours.do(scan_photos).tag('daily_scan')
        conn.commit()
    
    paths = conn.execute("SELECT * FROM scan_paths").fetchall()
    sets = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    conn.close()
    return render_template('admin.html', watched_paths=paths, settings=sets)

@app.route('/admin/scan_now', methods=['POST'])
def scan_now():
    if not is_scanning:
        threading.Thread(target=scan_photos).start()
    return redirect(url_for('admin'))

@app.route('/admin/scan_status')
def scan_status():
    return jsonify({"is_scanning": is_scanning})

@app.route('/admin/data_preview')
def data_preview():
    conn = get_db_connection()
    db_content = conn.execute("SELECT * FROM photos ORDER BY id DESC").fetchall()
    conn.close()
    if not db_content:
        return "<tr><td colspan='4' style='text-align:center; padding:20px;'>Database is empty.</td></tr>"
    html = ""
    for row in db_content:
        html += f"<tr><td>{row['pic_local_path']}</td><td>{row['gps_position']}</td><td>{row['city'] or '-'}</td><td>{row['country'] or '-'}</td></tr>"
    return html

@app.route('/admin/db_dump')
def db_dump():
    return send_file(DB_PATH, as_attachment=True)

@app.route('/admin/db_reset', methods=['POST'])
def db_reset():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM photos")
        conn.execute("DELETE FROM scan_paths")
        conn.execute("UPDATE settings SET last_run = NULL WHERE id = 1")
        conn.commit()
    return redirect(url_for('admin'))

@app.route('/full_image/<path:p>')
def full_image(p):
    return send_file('/' + p)

if __name__ == '__main__':
    init_db()
    # Load initial interval
    with get_db_connection() as c:
        row = c.execute("SELECT scan_interval_hours FROM settings WHERE id = 1").fetchone()
        interval = row[0] if row else 24
    
    schedule.every(interval).hours.do(scan_photos).tag('daily_scan')
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    app.run(host='0.0.0.0', port=5005)