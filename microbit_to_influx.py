#!/usr/bin/env python3
import threading, time, re, serial
from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient, Point

# — Config InfluxDB —
INFLUX_URL = "http://localhost:8086"
TOKEN      = "s5SFeety1Oicla2NKF_bjgUHIybWAkUNKJiNw6SS8-qbgtJo5kWgfBJ7K26X1eQnf1smfcLMqnHT5ZlwxXVXiA=="
ORG        = "microbit-org"
BUCKET     = "microbit"

# — Config Seriale —
COM_PORT  = "COM5"
BAUD_RATE = 115200

# — Pattern & Mapping —
MSG_PATTERN   = re.compile(r"(STATE;[^;]+;[^;]+;\d+|SENSOR;[^;]+;[01];\d+)")
STATE_MAPPING = {'VERDE':2,'GIALLO':1,'ROSSO':0}

# — Statistiche —
vias = ["Nord","Est","Sud"]
stats = {
    v: {
      'sensor_hits':0,
      'state_changes':0,
      'green_sum':0,
      'green_count':0,
      'green_start':None
    } for v in vias
}

# Influx client
influx = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
write_api = influx.write_api()

# Apri seriale
ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=0)
print(f"[ingest] Serial open {COM_PORT}")

def ingest_loop():
    buffer = ""
    while True:
        to_read = ser.in_waiting or 1
        data    = ser.read(to_read).decode('utf-8',errors='ignore')
        buffer += data

        while '\n' in buffer:
            line, buffer = buffer.split('\n',1)
            raw = line.strip()
            if not raw: continue

            msgs = MSG_PATTERN.findall(raw)
            for m in msgs:
                _, via, val, ts_dev = m.split(';')
                ts_dev = int(ts_dev)
                # STATISTICS
                if m.startswith("SENSOR;"):
                    if val=="1":
                        stats[via]['sensor_hits'] += 1
                else:  # STATE
                    stats[via]['state_changes'] += 1
                    # green timing
                    prev_start = stats[via]['green_start']
                    if val=="VERDE":
                        stats[via]['green_start'] = ts_dev
                    else:
                        if prev_start is not None:
                            duration = ts_dev - prev_start
                            stats[via]['green_sum']   += duration
                            stats[via]['green_count'] += 1
                            stats[via]['green_start'] = None

                # Write to InfluxDB as before
                if m.startswith("STATE;"):
                    num = STATE_MAPPING.get(val.upper())
                    if num is not None:
                        lp = f"stato_semaforo,via={via} stato={num}i"
                        write_api.write(bucket=BUCKET,org=ORG,record=lp)
                else:
                    flag = int(val)
                    p = Point("sensore_attivazione").tag("via",via).field("active",flag)
                    write_api.write(bucket=BUCKET,org=ORG,record=p)

            time.sleep(0.01)
        time.sleep(0.1)

# Flask per API night, emergency e stats
app = Flask(__name__)

def send_cmd(cmd):
    ser.write((cmd+"\n").encode())
    print(f"[cmd] {cmd}")

@app.route("/night_mode", methods=["POST"])
def night_mode():
    mode = request.json.get("mode","OFF").upper()
    if mode not in ("ON","OFF"):
        return jsonify(error="mode must be ON or OFF"),400
    send_cmd(f"CMD;NIGHT;{mode}")
    return jsonify(status="ok", mode=mode)

@app.route("/emergency", methods=["POST"])
def emergency():
    via  = request.json.get("via")
    mode = request.json.get("mode","OFF").upper()
    if via not in vias or mode not in ("ON","OFF"):
        return jsonify(error="via must be Nord/Est/Sud and mode ON/OFF"),400
    send_cmd(f"CMD;EMERGENCY;{via};{mode}")
    return jsonify(status="ok", via=via, mode=mode)

@app.route("/stats")
def get_stats():
    out = {}
    for v in vias:
        s = stats[v]
        avg = (s['green_sum']/s['green_count']) if s['green_count']>0 else 0
        out[v] = {
          'vehicles':       s['sensor_hits'],
          'changes':        s['state_changes'],
          'avg_green_ms':   int(avg)
        }
    return jsonify(out)

if __name__=="__main__":
    threading.Thread(target=ingest_loop, daemon=True).start()
    app.run(port=5001)
