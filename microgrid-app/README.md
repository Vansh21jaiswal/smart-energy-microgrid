# Smart Energy Microgrid & Demand Forecasting Engine

**HackSphere 3.0 Submission**

---

## Overview

An end-to-end web application that forecasts hourly energy demand for the next 24 hours using a **Zoho Catalyst QuickML** regression model, then applies smart grid-switching logic to dispatch power-source signals between a main utility grid and local renewable battery storage.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│               Catalyst Hosting (Slate)               │
│               public/index.html  (SPA)               │
│  Manual Form ─┐                                      │
│  CSV Upload  ─┤──► POST /forecast  ──► AppSail API   │
└───────────────┘                                      │
                                                       │
┌──────────────────────────────────────────────────────┤
│       Catalyst AppSail – Python 3.9 (Flask)          │
│  functions/forecast-api/app/main.py                  │
│    ├── predict(input_df)  ─► QuickML REST endpoint   │
│    │                         (Catalyst QuickML)       │
│    ├── controller()       ─► grid switching rules     │
│    └── estimate_battery_soc()  ─► SoC simulation     │
└──────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Status |
|---|---|
| 24-hour demand forecast via QuickML | ✅ |
| Manual telemetry form | ✅ |
| CSV file upload | ✅ |
| Grid controller logic | ✅ |
| Critical overload alert (≥ 200 kW) | ✅ |
| Interactive demand chart | ✅ |
| Battery SoC chart | ✅ |
| Hourly forecast table | ✅ |
| `predict(input_df)` contract preserved | ✅ |
| Zoho Catalyst AppSail deployment | ✅ |

---

## Controller Logic

| Condition | Action |
|---|---|
| Demand > 160 kW **OR** hour ∈ [18, 22] | **Renewable Storage Mode** |
| Otherwise | **Main Grid Mode** |
| Demand ≥ 200 kW | **Critical Overload Alert** (independent) |

---

## Local Development

### Prerequisites

```bash
pip install flask flask-cors pandas scikit-learn requests numpy gunicorn
```

### Run

```bash
cd microgrid-app/functions/forecast-api/app
python main.py
# → http://localhost:8080
```

Open `public/index.html` in your browser (served by Flask or any static server).

> **Note:** Set `window.FORECAST_API_BASE = "http://localhost:8080"` in browser console or hardcode it in `dashboard.js` when running locally with CORS.

### Test predict.py contract

```bash
cd HackSphere_Starter_Kit
python3 test_eval.py
# Expected output: SUCCESS
```

```bash
python3 predict.py --input sample_test_input.csv --output predictions.csv
```

---

## Environment Variables

The following variables are required. **Never commit secrets to public repos.**

| Variable | Description |
|---|---|
| `QUICKML_ENDPOINT_URL` | Published QuickML REST endpoint URL |
| `QUICKML_ENDPOINT_KEY` | QuickML endpoint authentication key |
| `CATALYST_ORG` | Zoho Catalyst organisation ID |
| `ZOHO_ACCESS_TOKEN` | Short-lived OAuth 2.0 access token |
| `CATALYST_ENVIRONMENT` | `Development` or `Production` |

Store in `.env` (gitignored) for local development. Set via Catalyst AppSail environment variables for production.

---

## Project Structure

```
hacksphere/
├── HackSphere_Starter_Kit/        # Original starter kit (unchanged)
│   ├── predict.py                 # QuickML + local RF model wrapper
│   ├── test_eval.py               # Pre-submission self-tester
│   ├── train_telemetry.csv
│   └── sample_test_input.csv
│
└── microgrid-app/                 # Full application
    ├── catalyst-config.json       # Catalyst project config
    ├── public/                    # Static frontend (Catalyst Hosting)
    │   ├── index.html
    │   ├── css/style.css
    │   └── js/dashboard.js
    └── functions/
        └── forecast-api/          # Catalyst AppSail Python service
            ├── requirements.txt
            ├── Procfile
            └── app/
                ├── main.py        # Flask API
                ├── predict.py     # (copy from starter kit)
                └── train_telemetry.csv
```

---

## Deployment (Zoho Catalyst)

1. Install the Catalyst CLI: `npm install -g zcatalyst-cli`
2. Authenticate: `catalyst login`
3. From the `microgrid-app/` directory:
   ```bash
   catalyst deploy
   ```
4. Set environment variables in the Catalyst AppSail console (never commit them).
5. The public URL will be shown after deployment completes.

---

## Submission Checklist

- [x] `predict.py` — working QuickML endpoint, `predict(input_df)` contract
- [x] `test_eval.py` — returns `SUCCESS`
- [x] Web dashboard — form, CSV upload, charts, controller badges, overload alert
- [x] `README.md` — architecture, setup, env vars
- [ ] Live Catalyst URL — requires manual `catalyst deploy` with your OAuth token

---

*All the best — HackSphere 3.0!*
