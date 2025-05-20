from dotenv import load_dotenv
import os
import pyotp
from flask import Flask, render_template, session, redirect, request, url_for, flash, jsonify
from flask_mail import Mail, Message
import sqlite3
import datetime
import requests
from functools import wraps
import time

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('HSERVER_SECRET_KEY', 'change-this-key')  # set in .env for production

# Secure session cookie settings
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,  # Only works with HTTPS
    SESSION_COOKIE_SAMESITE='Lax'
)

# Flask-Mail config from .env
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)

# Use env variable for password
APP_PASSWORD = os.environ.get('HSERVER_PASSWORD', 'change-this-password')  # set in .env for production
TOTP_SECRET = os.environ.get('HSERVER_2FA_SECRET', '')  # set in .env for production

# Lockout config
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes

DB_NAME = "sensor_data.db"

def get_latest_reading():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, temperature, humidity, aqi, gas_detected, motion_detected FROM readings ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row if row else ("--", "--", "--", "--", "--", "--")

def get_all_readings(limit=500):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, temperature, humidity, aqi, gas_detected, motion_detected FROM readings ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_last_detected(event_column):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT timestamp FROM readings WHERE {event_column}=1 ORDER BY id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def time_ago(dt_str):
    if not dt_str or dt_str == "--":
        return "Never"
    dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return f"{int(seconds)} sec ago"
    elif seconds < 3600:
        return f"{int(seconds//60)} min ago"
    elif seconds < 86400:
        return f"{int(seconds//3600)} hours ago"
    elif seconds < 2592000:
        return f"{int(seconds//86400)} days ago"
    elif seconds < 31536000:
        return f"{int(seconds//2592000)} months ago"
    else:
        return f"{int(seconds//31536000)} years ago"

def get_db_connection():
    return sqlite3.connect(DB_NAME)

def get_outdoor_location():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("SELECT value FROM settings WHERE key='outdoor_location'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "New York"

def set_outdoor_location(location):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("outdoor_location", location))
    conn.commit()
    conn.close()

def fetch_outdoor_data(location):
    # Uses WeatherAPI to fetch current weather data, including air quality
    API_KEY = "076ed9d30c1a49d9a22164631251505"
    url = f"http://api.weatherapi.com/v1/current.json?key={API_KEY}&q={location}&aqi=yes"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        temperature = data["current"]["temp_c"]
        humidity = data["current"]["humidity"]
        air_quality = data["current"].get("air_quality", {})
        pm2_5 = air_quality.get("pm2_5")
        if pm2_5 is not None:
            # Convert PM2.5 to AQI using EPA formula
            pm = float(pm2_5)
            if pm <= 12:
                aqi = int((50/12)*pm)
            elif pm <= 35.4:
                aqi = int(((100-51)/(35.4-12.1))*(pm-12.1)+51)
            elif pm <= 55.4:
                aqi = int(((150-101)/(55.4-35.5))*(pm-35.5)+101)
            elif pm <= 150.4:
                aqi = int(((200-151)/(150.4-55.5))*(pm-55.5)+151)
            elif pm <= 250.4:
                aqi = int(((300-201)/(250.4-150.5))*(pm-150.5)+201)
            elif pm <= 500.4:
                aqi = int(((500-301)/(500.4-250.5))*(pm-250.5)+301)
            else:
                aqi = 500
        else:
            aqi = "--"
        return {
            "temperature": temperature,
            "humidity": humidity,
            "aqi": aqi
        }
    except Exception:
        return {
            "temperature": "--",
            "humidity": "--",
            "aqi": "--"
        }

def get_email_alert_enabled():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("SELECT value FROM settings WHERE key='email_alert_enabled'")
    row = cursor.fetchone()
    conn.close()
    return row[0] == "1" if row else False

def set_email_alert_enabled(enabled: bool):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("email_alert_enabled", "1" if enabled else "0"))
    conn.commit()
    conn.close()

@app.route('/toggle_email_alert', methods=['POST'])
def toggle_email_alert():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    enabled = request.json.get('enabled', False)
    set_email_alert_enabled(enabled)
    return jsonify({'success': True, 'enabled': enabled})

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

ALERT_EMAIL_RECEIVER = os.environ.get('ALERT_EMAIL_RECEIVER')

def send_alert_email(event_type, timestamp):
    if not ALERT_EMAIL_RECEIVER:
        print("[!] ALERT_EMAIL_RECEIVER not set in .env")
        return
    subject = f"Home Server Alert: {event_type} Detected"
    body = f"Alert: {event_type} detected at {timestamp}.\n\nPlease check your Home Server Dashboard for details."
    try:
        msg = Message(subject, recipients=[ALERT_EMAIL_RECEIVER], body=body)
        mail.send(msg)
        print(f"[✓] Alert email sent to {ALERT_EMAIL_RECEIVER} for {event_type} at {timestamp}")
    except Exception as e:
        print(f"[X] Failed to send alert email: {e}")

def get_last_alerted(event_type):
    # Store last alert timestamp in settings table
    conn = get_db_connection()
    cursor = conn.cursor()
    key = f"last_alert_{event_type.lower()}"
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_last_alerted(event_type, timestamp):
    conn = get_db_connection()
    cursor = conn.cursor()
    key = f"last_alert_{event_type.lower()}"
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, timestamp))
    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    # if 'logged_in' not in session:
    #     return redirect(url_for('login'))

    if request.method == 'POST':
        location = request.form.get('location')
        if location:
            set_outdoor_location(location)
    outdoor_location = get_outdoor_location()
    outdoor = fetch_outdoor_data(outdoor_location)

    latest = get_latest_reading()
    history = get_all_readings()
    last_gas_time = get_last_detected('gas_detected')
    last_motion_time = get_last_detected('motion_detected')
    last_gas_ago = time_ago(last_gas_time)
    last_motion_ago = time_ago(last_motion_time)
    email_alert_enabled = get_email_alert_enabled()

    # --- Email Alert Logic ---
    if email_alert_enabled:
        # latest = (timestamp, temp, humidity, aqi, gas_detected, motion_detected)
        if latest[4] == 1:  # Gas Detected
            last_alert = get_last_alerted("Gas")
            if last_alert != latest[0]:
                send_alert_email("Gas", latest[0])
                set_last_alerted("Gas", latest[0])
        if latest[5] == 1:  # Motion Detected
            last_alert = get_last_alerted("Motion")
            if last_alert != latest[0]:
                send_alert_email("Motion", latest[0])
                set_last_alerted("Motion", latest[0])
    # --- End Email Alert Logic ---

    return render_template(
        "index.html",
        latest=latest,
        history=history,
        last_gas_time=last_gas_time,
        last_motion_time=last_motion_time,
        last_gas_ago=last_gas_ago,
        last_motion_ago=last_motion_ago,
        outdoor=outdoor,
        outdoor_location=outdoor_location,
        email_alert_enabled=email_alert_enabled
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Track failed attempts in session
    if 'failed_attempts' not in session:
        session['failed_attempts'] = 0
    if 'lockout_until' in session:
        if time.time() < session['lockout_until']:
            wait = int(session['lockout_until'] - time.time())
            return render_template("login.html", error=f"Account locked. Try again in {wait} seconds.", require_2fa=False)
        else:
            session.pop('lockout_until')

    # 2FA step: If password is correct, ask for 2FA code in a separate step
    if request.method == 'POST':
        if session.get('2fa_pending'):
            totp_code = request.form.get('totp')
            if TOTP_SECRET:
                totp = pyotp.TOTP(TOTP_SECRET)
                if totp_code and totp.verify(totp_code, valid_window=1):
                    session['logged_in'] = True
                    session['failed_attempts'] = 0
                    session.pop('2fa_pending', None)
                    return redirect(url_for('index'))
                else:
                    return render_template("login.html", error="Invalid 2FA code.", require_2fa=True)
            else:
                # Should not happen, but fallback
                session['logged_in'] = True
                session['failed_attempts'] = 0
                session.pop('2fa_pending', None)
                return redirect(url_for('index'))
        else:
            password = request.form.get('password')
            if not password:
                return "Missing password", 400

            if password == APP_PASSWORD:
                if TOTP_SECRET:
                    session['2fa_pending'] = True
                    return render_template("login.html", error=None, require_2fa=True)
                else:
                    session['logged_in'] = True
                    session['failed_attempts'] = 0
                    return redirect(url_for('index'))
            else:
                session['failed_attempts'] += 1
                if session['failed_attempts'] >= MAX_FAILED_ATTEMPTS:
                    session['lockout_until'] = time.time() + LOCKOUT_SECONDS
                    return render_template("login.html", error="Too many failed attempts. Account locked for 5 minutes.", require_2fa=False)
                return render_template("login.html", error="Incorrect password.", require_2fa=False)
    # GET request
    return render_template("login.html", error=None, require_2fa=session.get('2fa_pending', False))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/demo')
def demo():
    # Dummy data for demo mode
    latest = ("2024-06-01 12:00:00", "34.0", "69.0", "100", "0", "0")
    history = [
        ("2024-06-01 12:00:00", "34.0", "69.0", "100", 0, 0),
        ("2024-06-01 11:00:00", "33.5", "68.0", "98", 0, 0),
        ("2024-06-01 10:00:00", "33.0", "67.0", "95", 0, 0),
    ]
    last_gas_time = "2024-05-31 18:00:00"
    last_motion_time = "2024-05-31 19:00:00"
    last_gas_ago = "6 hours ago"
    last_motion_ago = "5 hours ago"
    outdoor = {"temperature": "34.0", "humidity": "69.0", "aqi": "100"}
    outdoor_location = "Demo City"
    email_alert_enabled = False
    return render_template(
        "index.html",
        latest=latest,
        history=history,
        last_gas_time=last_gas_time,
        last_motion_time=last_motion_time,
        last_gas_ago=last_gas_ago,
        last_motion_ago=last_motion_ago,
        outdoor=outdoor,
        outdoor_location=outdoor_location,
        email_alert_enabled=email_alert_enabled,
        demo_mode=True
    )

@app.route('/api/latest')
@login_required
def api_latest():
    latest = get_latest_reading()
    outdoor_location = get_outdoor_location()
    outdoor = fetch_outdoor_data(outdoor_location)
    last_gas_time = get_last_detected('gas_detected')
    last_motion_time = get_last_detected('motion_detected')
    last_gas_ago = time_ago(last_gas_time)
    last_motion_ago = time_ago(last_motion_time)
    return jsonify({
        "latest": {
            "time": latest[0],
            "temperature": latest[1],
            "humidity": latest[2],
            "aqi": latest[3]
        },
        "outdoor": outdoor,
        "last_gas_ago": last_gas_ago,
        "last_motion_ago": last_motion_ago
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
