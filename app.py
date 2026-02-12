import os, sqlite3, threading, exifread, time, schedule, io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import ssl
import certifi
import geopy.geocoders
from geopy.geocoders import Nominatim

# Initialize Flask
app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'photos.db')

# --- GLOBAL SCAN STATE ---
scan_status_info = {
    "active": False,
    "percentage": 0,
    "current_file": "",
    "stop_requested": False,
    "last_run": "Never"
}

# Comprehensive mapping of country codes - to be moved in separate file
ISO2_TO_ISO3 = {
    "AF": "AFG", "AL": "ALB", "DZ": "DZA", "AS": "ASM", "AD": "AND", "AO": "AGO", "AI": "AIA", "AQ": "ATA", "AG": "ATG", "AR": "ARG",
    "AM": "ARM", "AW": "ABW", "AU": "AUS", "AT": "AUT", "AZ": "AZE", "BS": "BHS", "BH": "BHR", "BD": "BGD", "BB": "BRB", "BY": "BLR",
    "BE": "BEL", "BZ": "BLZ", "BJ": "BEN", "BM": "BMU", "BT": "BTN", "BO": "BOL", "BA": "BIH", "BW": "BWA", "BR": "BRA", "BN": "BRN",
    "BG": "BGR", "BF": "BFA", "BI": "BDI", "KH": "KHM", "CM": "CMR", "CA": "CAN", "CV": "CPV", "KY": "CYM", "CF": "CAF", "TD": "TCD",
    "CL": "CHL", "CN": "CHN", "CO": "COL", "KM": "COM", "CG": "COG", "CD": "COD", "CR": "CRI", "CI": "CIV", "HR": "HRV", "CU": "CUB",
    "CY": "CYP", "CZ": "CZE", "DK": "DNK", "DJ": "DJI", "DM": "DMA", "DO": "DOM", "EC": "ECU", "EG": "EGY", "SV": "SLV", "GQ": "GNQ",
    "ER": "ERI", "EE": "EST", "ET": "ETH", "FJ": "FJI", "FI": "FIN", "FR": "FRA", "GA": "GAB", "GM": "GMB", "GE": "GEO", "DE": "DEU",
    "GH": "GHA", "GR": "GRC", "GD": "GRD", "GU": "GUM", "GT": "GTM", "GN": "GIN", "GW": "GNB", "GY": "GUY", "HT": "HTI", "HN": "HND",
    "HK": "HKG", "HU": "HUN", "IS": "ISL", "IN": "IND", "ID": "IDN", "IR": "IRN", "IQ": "IRQ", "IE": "IRL", "IL": "ISR", "IT": "ITA",
    "JM": "JAM", "JP": "JPN", "JO": "JOR", "KZ": "KAZ", "KE": "KEN", "KI": "KIR", "KP": "PRK", "KR": "KOR", "KW": "KWT", "KG": "KGZ",
    "LA": "LAO", "LV": "LVA", "LB": "LBN", "LS": "LSO", "LR": "LBR", "LY": "LBY", "LI": "LIE", "LT": "LTU", "LU": "LUX", "MO": "MAC",
    "MK": "MKD", "MG": "MDG", "MW": "MWI", "MY": "MYS", "MV": "MDV", "ML": "MLI", "MT": "MLT", "MH": "MHL", "MQ": "MTQ", "MR": "MRT",
    "MU": "MUS", "MX": "MEX", "MD": "MDA", "MC": "MCO", "MN": "MNG", "ME": "MNE", "MS": "MSR", "MA": "MAR", "MZ": "MOZ", "MM": "MMR",
    "NA": "NAM", "NR": "NRU", "NP": "NPL", "NL": "NLD", "NZ": "NZL", "NI": "NIC", "NE": "NER", "NG": "NGA", "NO": "NOR", "OM": "OMN",
    "PK": "PAK", "PW": "PLW", "PS": "PSE", "PA": "PAN", "PG": "PNG", "PY": "PRY", "PE": "PER", "PH": "PHL", "PN": "PCN", "PL": "POL",
    "PT": "PRT", "PR": "PRI", "QA": "QAT", "RE": "REU", "RO": "ROU", "RU": "RUS", "RW": "RWA", "KN": "KNA", "LC": "LCA", "VC": "VCT",
    "WS": "WSM", "SM": "SMR", "ST": "STP", "SA": "SAU", "SN": "SEN", "RS": "SRB", "SC": "SYC", "SL": "SLE", "SG": "SGP", "SK": "SVK",
    "SI": "SVN", "SB": "SLB", "SO": "SOM", "ZA": "ZAF", "ES": "ESP", "LK": "LKA", "SD": "SDN", "SR": "SUR", "SZ": "SWZ", "SE": "SWE",
    "CH": "CHE", "SY": "SYR", "TW": "TWN", "TJ": "TJK", "TZ": "TZA", "TH": "THA", "TG": "TGO", "TO": "TON", "TT": "TTO", "TN": "TUN",
    "TR": "TUR", "TM": "TKM", "TV": "TUV", "UG": "UGA", "UA": "UKR", "AE": "ARE", "GB": "GBR", "US": "USA", "UY": "URY", "UZ": "UZB",
    "VU": "VUT", "VA": "VAT", "VE": "VEN", "VN": "VNM", "YE": "YEM", "ZM": "ZMB", "ZW": "ZWE"
}

dry_run_stop_requested = False

# SSL Context for Geopy on Synology
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
            city TEXT, county TEXT, state TEXT, country TEXT, country_code TEXT,
            folder_name TEXT,
            date_taken TEXT
        )''')
        conn.execute('CREATE TABLE IF NOT EXISTS scan_paths (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE)')
        conn.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, scan_interval_hours INTEGER DEFAULT 24, last_run TEXT)')
        conn.execute("INSERT OR IGNORE INTO settings (id, scan_interval_hours) VALUES (1, 24)")
        conn.commit()

# --- GPS & EXIF EXTRACTION ---

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

def extract_date_taken(path):
    try:
        with open(path, 'rb') as f:
            tags = exifread.process_file(f, stop_tag='DateTimeOriginal', details=False)
            dt_tag = tags.get('EXIF DateTimeOriginal') or tags.get('Image DateTime')
            return str(dt_tag) if dt_tag else None
    except: return None

# --- CORE SCANNING LOGIC ---

def scan_photos_task():
    global scan_status_info
    if scan_status_info["active"]: return
    
    scan_status_info["active"] = True
    scan_status_info["stop_requested"] = False
    scan_status_info["percentage"] = 0
    
    conn = get_db_connection()
    paths = [row['path'] for row in conn.execute("SELECT path FROM scan_paths").fetchall()]
    
    all_files = []
    for base_path in paths:
        if not os.path.exists(base_path): continue
        for root, _, files in os.walk(base_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg')):
                    all_files.append(os.path.join(root, file))
    
    total_files = len(all_files)
    
    for index, full_path in enumerate(all_files):
        if scan_status_info["stop_requested"]: break
            
        scan_status_info["current_file"] = os.path.basename(full_path)
        if total_files > 0:
            scan_status_info["percentage"] = int(((index + 1) / total_files) * 100)

        if not conn.execute("SELECT 1 FROM photos WHERE pic_local_path=?", (full_path,)).fetchone():
            gps = extract_gps(full_path)
            if gps:
                folder_name = os.path.basename(os.path.dirname(full_path))
                date_taken = extract_date_taken(full_path)
                try:
                    loc = geolocator.reverse(gps, language='en', timeout=10)
                    addr = loc.raw.get('address', {})
                    raw_code = addr.get('country_code', '').upper()
                    
                    country_iso_3 = ISO2_TO_ISO3.get(raw_code)

                    conn.execute("""INSERT INTO photos (pic_local_path, gps_position, city, county, state, country, country_code, folder_name, date_taken) 
                                    VALUES (?,?,?,?,?,?,?,?,?)""",
                                (full_path, gps, 
                                 addr.get('city') or addr.get('town') or addr.get('village'), 
                                 addr.get('county'),
                                 addr.get('state'), addr.get('country'),
                                 country_iso_3, folder_name, date_taken))
                    conn.commit()
                    time.sleep(1.1) # Respect Nominatim usage policy
                except Exception as e:
                    print(f"Geocoding error for {full_path}: {e}")
    
    last_run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE settings SET last_run = ? WHERE id = 1", (last_run_time,))
    conn.commit()
    conn.close()
    
    scan_status_info["active"] = False
    scan_status_info["last_run"] = last_run_time

# --- BACKGROUND SCHEDULER ---

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

# --- FLASK ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    # Fetch unique pairs for the map
    rows = conn.execute("SELECT DISTINCT country_code, country FROM photos WHERE country_code IS NOT NULL").fetchall()
    visited_data = [{"code": r["country_code"], "name": r["country"]} for r in rows]
    
    results = []
    query = request.form.get('query', '')
    if query:
        lq = f"%{query}%"
        results = conn.execute("""SELECT * FROM photos WHERE city LIKE ? OR county LIKE ?
                                  OR state LIKE ? 
                                  OR country LIKE ? OR folder_name LIKE ?""", (lq, lq, lq, lq, lq)).fetchall()
    conn.close()
    return render_template('index.html', results=results, query=query, visited_data=visited_data)

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
            schedule.every(hrs).hours.do(scan_photos_task).tag('daily_scan')
        conn.commit()
    
    paths = conn.execute("SELECT * FROM scan_paths").fetchall()
    sets = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    conn.close()
    return render_template('admin.html', watched_paths=paths, settings=sets, scan_info=scan_status_info)

@app.route('/start_scan', methods=['POST'])
def start_scan():
    if not scan_status_info["active"]:
        threading.Thread(target=scan_photos_task).start()
    return jsonify({"status": "started"})

@app.route('/stop_scan', methods=['POST'])
def stop_scan():
    scan_status_info["stop_requested"] = True
    return jsonify({"status": "stopping"})

@app.route('/scan_progress')
def scan_progress():
    return jsonify(scan_status_info)

@app.route('/admin/data_preview')
def data_preview():
    conn = get_db_connection()
    db_content = conn.execute("SELECT * FROM photos ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    if not db_content:
        return "<tr><td colspan='6' style='text-align:center;'>Database is empty.</td></tr>"
    html = ""
    for row in db_content:
        html += f"<tr><td>{row['folder_name']}</td><td>{os.path.basename(row['pic_local_path'])}</td><td>{row['date_taken'] or '-'}</td><td>{row['city'] or '-'}</td><td>{row['county'] or '-'}</td><td>{row['state'] or '-'}</td><td>{row['country'] or '-'}</td></tr>"
    return html

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

@app.route('/admin/dry_run', methods=['POST'])
def dry_run():
    global dry_run_stop_requested
    dry_run_stop_requested = False
    data = request.json
    folder_path = data.get('path')
    offset = data.get('offset', 0)
    limit = 20
    
    if not os.path.exists(folder_path):
        return jsonify({"error": "Path not found"}), 400

    all_files = []
    for root, _, files in os.walk(folder_path):
        for file in sorted(files):
            if file.lower().endswith(('.jpg', '.jpeg')):
                all_files.append(os.path.join(root, file))
    
    total_count = len(all_files)
    batch_files = all_files[offset : offset + limit]
    
    results = []
    for fp in batch_files:
        if dry_run_stop_requested: break
        gps = extract_gps(fp)
        folder = os.path.basename(os.path.dirname(fp))
        date = extract_date_taken(fp)
        
        res_item = {"name": os.path.basename(fp), "gps": gps or "No GPS", "city": "-", "country": "-", "folder": folder, "date": date or "Unknown"}
        if gps:
            try:
                loc = geolocator.reverse(gps, language='en', timeout=5)
                addr = loc.raw.get('address', {})
                print(loc.raw)
                res_item["city"] = addr.get('city') or addr.get('town') or "-"
                res_item["country"] = addr.get('country') or "-"
            except: pass
        results.append(res_item)

    new_offset = offset + len(batch_files)
    return jsonify({
        "results": results, 
        "offset": new_offset, 
        "total": total_count,
        "finished": new_offset >= total_count or dry_run_stop_requested
    })

@app.route('/admin/stop_dry_run', methods=['POST'])
def stop_dry_run():
    global dry_run_stop_requested
    dry_run_stop_requested = True
    return jsonify({"status": "stopping"})

if __name__ == '__main__':
    init_db()
    with get_db_connection() as c:
        row = c.execute("SELECT scan_interval_hours, last_run FROM settings WHERE id = 1").fetchone()
        interval = row[0] if row else 24
        scan_status_info["last_run"] = row[1] if row and row[1] else "Never"
    
    schedule.every(interval).hours.do(scan_photos_task).tag('daily_scan')
    threading.Thread(target=run_scheduler, daemon=True).start()
    app.run(host='0.0.0.0', port=5005)