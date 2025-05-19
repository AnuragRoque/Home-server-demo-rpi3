import serial
import time
import sqlite3
from datetime import datetime

# Setup
COM_PORT = 'COM7'
BAUD_RATE = 115200
DB_NAME = "sensor_data.db"

# Initialize DB
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        temperature REAL,
        humidity REAL,
        aqi INTEGER,
        gas_detected INTEGER,
        motion_detected INTEGER
    )
''')
conn.commit()

# Serial read + store loop
try:
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    print(f"[✓] Connected to {COM_PORT}")
    time.sleep(2)

    # Send soft reboot (Ctrl+D)
    ser.write(b'\x04')  # Ctrl+D = soft reboot in REPL
    print("[✓] Sent soft reboot command")
    time.sleep(2)  # Wait for the device to reboot

    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            if line:
                try:
                    temp, humidity, aqi, gas_detected, motion_detected = map(int, line.split(","))
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute("INSERT INTO readings (timestamp, temperature, humidity, aqi, gas_detected, motion_detected) VALUES (?, ?, ?, ?, ?, ?)",
                              (now, temp, humidity, aqi, gas_detected, motion_detected))
                    conn.commit()
                    print(f"[✓] Logged: {now} - {temp}°C, {humidity}%, AQI: {aqi}, Gas Detected: {gas_detected}, Motion Detected: {motion_detected}")
                except ValueError:
                    print(f"[!] Invalid data: {line}")
except serial.SerialException as e:
    print(f"[X] Could not open {COM_PORT}: {e}")
finally:
    conn.close()
    if 'ser' in locals():
        ser.close()
