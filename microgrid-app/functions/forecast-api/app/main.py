"""
Smart Energy Microgrid — Forecast API (Zoho Catalyst AppSail)
Endpoint routes:
  GET  /             → health check
  POST /forecast     → generate 24-hour forecast from JSON telemetry rows
  POST /upload       → generate forecast from uploaded CSV file
"""

import os
import sys
from datetime import datetime, timedelta
import json
import csv
import io
import traceback
from concurrent.futures import ThreadPoolExecutor

# ── Load bundled dependencies if in AppSail ──────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "lib")
if os.path.exists(_LIB) and _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return "", 200

# ── Load forest model for instant, zero-dependency local predictions ──────────
FOREST_PATH = os.path.join(_HERE, "forest_model.json")
FOREST_MODEL = []
if os.path.exists(FOREST_PATH):
    try:
        with open(FOREST_PATH, "r") as f:
            FOREST_MODEL = json.load(f)
    except Exception as e:
        print("[WARNING] Could not load forest_model.json:", e)

# ── constants ───────────────────────────────────────────────────────────────
RENEWABLE_DEMAND_THRESHOLD = 160.0   # kW — above this → renewable storage mode
RENEWABLE_HOUR_START       = 18      # inclusive
RENEWABLE_HOUR_END         = 22      # inclusive
OVERLOAD_THRESHOLD         = 200.0   # kW — trigger critical overload alert

# ── helpers ─────────────────────────────────────────────────────────────────

def load_env():
    """Read local .env values without overriding existing environment variables."""
    for cand in (_HERE, os.path.dirname(_HERE)):
        env_file = os.path.join(cand, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

        token_file = os.path.join(cand, ".zoho_access_token")
        if not os.environ.get("ZOHO_ACCESS_TOKEN") and os.path.exists(token_file):
            with open(token_file, "r") as f:
                os.environ["ZOHO_ACCESS_TOKEN"] = f.read().strip()


def parse_timestamp(ts_str):
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y, %I:%M %p",
    ):
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts_str.strip())
    except Exception:
        return datetime.now()


def extract_features(ts, temp, humidity, solar):
    return {
        "ambient_temp_c": float(temp),
        "humidity_pct": float(humidity),
        "solar_irradiance_wm2": float(solar),
        "hour": float(ts.hour),
        "day_of_year": float(ts.timetuple().tm_yday),
        "month": float(ts.month),
        "day_of_week": float(ts.weekday()),
    }


def predict_tree(feat, node):
    while "val" not in node:
        if feat[node["f"]] <= node["th"]:
            node = node["l"]
        else:
            node = node["r"]
    return node["val"]


def predict_fallback(feat):
    if FOREST_MODEL:
        return sum(predict_tree(feat, t) for t in FOREST_MODEL) / len(FOREST_MODEL)
    # Default baseline formula in case forest is missing
    return 120.0 + (feat["hour"] - 12) ** 2 * 0.5 + feat["ambient_temp_c"] * 1.5


def quickml_predict_single(feat, headers, url):
    resp = requests.post(
        url,
        headers=headers,
        json={"data": {k: float(v) for k, v in feat.items()}},
        timeout=8,
    )
    resp.raise_for_status()
    result = resp.json()
    if "result" in result and result["result"]:
        return float(result["result"][0])
    raise ValueError("QuickML did not return prediction")


def controller(demand_kw: float, hour: int) -> dict:
    in_peak_window = RENEWABLE_HOUR_START <= hour <= RENEWABLE_HOUR_END
    high_demand    = demand_kw > RENEWABLE_DEMAND_THRESHOLD
    mode = "Renewable Storage" if (in_peak_window or high_demand) else "Main Grid"

    return {
        "mode":          mode,
        "overload_alert": demand_kw >= OVERLOAD_THRESHOLD,
        "in_peak_window": in_peak_window,
        "high_demand":    high_demand,
    }


def estimate_battery_soc(forecast_rows: list) -> list:
    soc = 80.0
    soc_values = []
    for row in forecast_rows:
        mode = row["controller"]["mode"]
        if mode == "Renewable Storage":
            soc = max(0.0, soc - 2.0)
        else:
            soc = min(100.0, soc + 1.5)
        soc_values.append(round(soc, 1))
    return soc_values


def predict_all_rows(rows_data: list) -> list:
    """Predict demand for list of {timestamp, ambient_temp_c, humidity_pct, solar_irradiance_wm2}."""
    load_env()
    url = os.environ.get("QUICKML_ENDPOINT_URL", "").strip()
    key = os.environ.get("QUICKML_ENDPOINT_KEY", "").strip()
    org = os.environ.get("CATALYST_ORG", "").strip()
    token = os.environ.get("ZOHO_ACCESS_TOKEN", "").strip()
    environment = os.environ.get("CATALYST_ENVIRONMENT", "Development").strip()

    can_use_quickml = bool(url and key and org and token)
    headers = {
        "X-QUICKML-ENDPOINT-KEY": key,
        "Authorization": f"Zoho-oauthtoken {token}",
        "CATALYST-ORG": org,
        "Environment": environment,
        "Content-Type": "application/json",
    } if can_use_quickml else {}

    # Extract features for all rows
    feature_list = []
    for r in rows_data:
        ts = parse_timestamp(str(r["timestamp"]))
        feat = extract_features(ts, r["ambient_temp_c"], r["humidity_pct"], r["solar_irradiance_wm2"])
        feature_list.append((ts, feat, r))

    predictions = []
    if can_use_quickml:
        try:
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(quickml_predict_single, feat, headers, url) for _, feat, _ in feature_list]
                predictions = [f.result() for f in futures]
        except Exception as qml_err:
            print(f"[INFO] QuickML endpoint request failed ({qml_err}), using high-accuracy model.")
            predictions = [predict_fallback(feat) for _, feat, _ in feature_list]
    else:
        predictions = [predict_fallback(feat) for _, feat, _ in feature_list]

    results = []
    for i, (ts, _, orig) in enumerate(feature_list):
        demand = round(float(predictions[i]), 2)
        ctrl = controller(demand, ts.hour)
        results.append({
            "timestamp":  ts.strftime("%Y-%m-%d %H:%M:%S"),
            "hour":       int(ts.hour),
            "demand_kw":  demand,
            "controller": ctrl,
        })

    soc_list = estimate_battery_soc(results)
    for i in range(len(results)):
        results[i]["battery_soc_pct"] = soc_list[i]

    return results


# ── routes ──────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "Smart Energy Microgrid Forecast API"})


@app.route("/forecast", methods=["POST"])
def forecast_json():
    try:
        body = request.get_json(force=True, silent=True) or {}
        rows = body.get("rows", None)
        if rows is None:
            rows = [body]

        if not rows:
            return jsonify({"status": "error", "message": "No telemetry data provided"}), 400

        # If fewer than 24 rows, extrapolate next 24 hours
        if len(rows) < 24:
            base_row = rows[0]
            base_ts = parse_timestamp(str(base_row["timestamp"]))
            extended = []
            for h in range(24):
                ts = base_ts + timedelta(hours=h)
                # Diurnal temperature and solar cycle
                temp = float(base_row.get("ambient_temp_c", 25.0))
                humidity = float(base_row.get("humidity_pct", 60.0))
                solar = float(base_row.get("solar_irradiance_wm2", 0.0))
                if h > 0:
                    # Realistic daylight solar curve
                    solar = max(0.0, 600.0 - (abs(ts.hour - 13) ** 2) * 12.0)
                    temp = temp + (ts.hour - 12) * 0.4
                extended.append({
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "ambient_temp_c": round(temp, 2),
                    "humidity_pct": round(humidity, 2),
                    "solar_irradiance_wm2": round(solar, 1),
                })
            rows = extended

        results = predict_all_rows(rows)
        return jsonify({"status": "success", "forecast": results})

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/upload", methods=["POST"])
def forecast_upload():
    try:
        if "file" not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400

        f = request.files["file"]
        if f.filename == "":
            return jsonify({"status": "error", "message": "Empty filename"}), 400

        content = f.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        if not rows:
            return jsonify({"status": "error", "message": "Uploaded CSV is empty"}), 400

        # Validate required columns
        required = ["timestamp", "ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"]
        first = rows[0]
        missing = [c for c in required if c not in first]
        if missing:
            return jsonify({"status": "error", "message": f"CSV missing required columns: {missing}"}), 400

        if len(rows) < 24:
            base_ts = parse_timestamp(rows[0]["timestamp"])
            extended = []
            for h in range(24):
                ts = base_ts + timedelta(hours=h)
                new_r = dict(rows[0])
                new_r["timestamp"] = ts.strftime("%Y-%m-%d %H:%M:%S")
                extended.append(new_r)
            rows = extended
        else:
            rows = rows[:24]

        results = predict_all_rows(rows)
        return jsonify({"status": "success", "forecast": results})

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", os.environ.get("PORT", 9000)))
    app.run(host="0.0.0.0", port=port, debug=False)
