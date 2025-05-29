from flask import Flask, render_template, request, jsonify
import requests
from influxdb_client import InfluxDBClient

# ── SEZIONE 1: CONFIGURAZIONE GENERALE ─────────────────────────────────────
# URL e token per connettersi a InfluxDB
INFLUX_URL       = "http://localhost:8086"
TOKEN            = "s5SF…XiA=="               # token di scrittura/query
ORG              = "microbit-org"
BUCKET           = "microbit"

# URL e identificatori per Grafana
GRAFANA_URL      = "http://localhost:3000"
DASHBOARD_UID    = "075b9381-2df1-4d19-8b33-ad212d2f2531"
DASHBOARD_SLUG   = "semaforo-intelligente"
PANEL_ID_STATO   = 1
PANEL_ID_SENSORE = 2

# ── SEZIONE 2: CLIENT INFLUXDB ──────────────────────────────────────────────
# Inizializza il client InfluxDB e l’API per le query
influx_client = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
query_api     = influx_client.query_api()

# ── SEZIONE 3: SETUP FLASK APP ─────────────────────────────────────────────
app = Flask(__name__)

# ── SEZIONE 4: HOME ROUTE ──────────────────────────────────────────────────
@app.route("/")
def index():
    # Ritorna la pagina HTML principale, passando le variabili per l’embed di Grafana
    return render_template("index.html",
        grafana_url      = GRAFANA_URL,
        dashboard_uid    = DASHBOARD_UID,
        dashboard_slug   = DASHBOARD_SLUG,
        panel_id_stato   = PANEL_ID_STATO,
        panel_id_sensore = PANEL_ID_SENSORE
    )

# ── SEZIONE 5: API PER STATI SEMAFORI ──────────────────────────────────────
@app.route("/api/stati")
def api_stati():
    # Parametri query: via (Nord/Est/Sud) e range temporale (es. -5m)
    via      = request.args.get("via", "Nord")
    duration = request.args.get("range", "-5m")
    # Costruzione della query Flux per InfluxDB
    flux = f"""
    from(bucket:"{BUCKET}")
      |> range(start:{duration})
      |> filter(fn:(r)=> r._measurement=="stato_semaforo")
      |> filter(fn:(r)=> r.via=="{via}")
    """
    # Esecuzione della query e raccolta dei risultati
    tables = query_api.query(flux)
    data = []
    for table in tables:
        for rec in table.records:
            data.append({
                "time":  rec.get_time().isoformat(),
                "value": rec.get_value()
            })
    return jsonify(data)

# ── SEZIONE 6: API PER STATI SENSORI ───────────────────────────────────────
@app.route("/api/sensori")
def api_sensori():
    via      = request.args.get("via", "Nord")
    duration = request.args.get("range", "-5m")
    flux = f"""
    from(bucket:"{BUCKET}")
      |> range(start:{duration})
      |> filter(fn:(r)=> r._measurement=="sensore_attivazione")
      |> filter(fn:(r)=> r.via=="{via}")
    """
    tables = query_api.query(flux)
    data = []
    for table in tables:
        for rec in table.records:
            data.append({
                "time":  rec.get_time().isoformat(),
                "value": rec.get_value()
            })
    return jsonify(data)

# ── SEZIONE 7: API PER MODALITÀ NOTTE ─────────────────────────────────────
@app.route("/api/night_mode", methods=["POST"])
def api_night_mode():
    # Riceve JSON {"mode":"ON"|"OFF"} e lo inoltra al servizio di ingest (porta 5001)
    data = request.json or {}
    mode = data.get("mode", "OFF").upper()
    resp = requests.post("http://localhost:5001/night_mode",
                         json={"mode": mode})
    return jsonify(resp.json()), resp.status_code

# ── SEZIONE 8: API PER MODALITÀ EMERGENZA ─────────────────────────────────
@app.route("/api/emergency", methods=["POST"])
def api_emergency():
    # Riceve JSON {"via":"Nord/Est/Sud", "mode":"ON"|"OFF"}
    data = request.json or {}
    via  = data.get("via")
    mode = data.get("mode", "OFF").upper()
    resp = requests.post("http://localhost:5001/emergency",
                         json={"via": via, "mode": mode})
    return jsonify(resp.json()), resp.status_code

# ── SEZIONE 9: API PER STATISTICHE ────────────────────────────────────────
@app.route("/stats")
def api_stats():
    # Proxy della chiamata al servizio ingest che espone /stats su porta 5001
    resp = requests.get("http://localhost:5001/stats")
    return (resp.text, resp.status_code, {'Content-Type': 'application/json'})

# ── SEZIONE 10: ENTRY POINT ────────────────────────────────────────────────
if __name__ == "__main__":
    # Avvia il server Flask in modalità di debug (riavvi automatico su modifica)
    app.run(debug=True)
