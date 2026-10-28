import argparse
import os
from pathlib import Path

import pandas as pd
import requests
from sklearn.ensemble import RandomForestRegressor

BASE_DIR = Path(__file__).resolve().parent

FEATURES = [
    "ambient_temp_c",
    "humidity_pct",
    "solar_irradiance_wm2",
    "hour",
    "day_of_year",
    "month",
    "day_of_week",
]


def load_env():
    """Read local .env values without overriding existing environment variables."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

    token_file = BASE_DIR / ".zoho_access_token"
    if not os.environ.get("ZOHO_ACCESS_TOKEN") and token_file.exists():
        os.environ["ZOHO_ACCESS_TOKEN"] = token_file.read_text().strip()


def make_features(df):
    x = df.copy()
    ts = pd.to_datetime(x["timestamp"], errors="coerce")
    if ts.isna().any():
        raise ValueError("Invalid or missing timestamp found.")

    x["hour"] = ts.dt.hour
    x["day_of_year"] = ts.dt.dayofyear
    x["month"] = ts.dt.month
    x["day_of_week"] = ts.dt.dayofweek
    return x[FEATURES].astype(float)


def local_predict(input_df):
    train_file = BASE_DIR / "train_telemetry.csv"
    train = pd.read_csv(train_file)

    model = RandomForestRegressor(
        n_estimators=200,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(make_features(train), train["target_demand_kw"].astype(float))
    return model.predict(make_features(input_df))


def quickml_predict(input_df):
    load_env()

    url = os.environ.get("QUICKML_ENDPOINT_URL", "").strip()
    key = os.environ.get("QUICKML_ENDPOINT_KEY", "").strip()
    org = os.environ.get("CATALYST_ORG", "").strip()
    token = os.environ.get("ZOHO_ACCESS_TOKEN", "").strip()
    environment = os.environ.get("CATALYST_ENVIRONMENT", "Development").strip()

    if not all([url, key, org, token]):
        raise RuntimeError(
            "QuickML configuration incomplete. Check .env and .zoho_access_token."
        )

    headers = {
        "X-QUICKML-ENDPOINT-KEY": key,
        "Authorization": f"Zoho-oauthtoken {token}",
        "CATALYST-ORG": org,
        "Environment": environment,
        "Content-Type": "application/json",
    }

    features = make_features(input_df)
    predictions = []

    # The tested QuickML endpoint accepts one feature object per request.
    for _, row in features.iterrows():
        response = requests.post(
            url,
            headers=headers,
            json={"data": {k: float(v) for k, v in row.items()}},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        if "result" not in result or not result["result"]:
            raise ValueError("QuickML response did not contain a prediction.")

        predictions.append(float(result["result"][0]))

    return predictions


def predict(input_df: pd.DataFrame):
    """Return one predicted demand value per input row."""
    required = [
        "timestamp",
        "ambient_temp_c",
        "humidity_pct",
        "solar_irradiance_wm2",
    ]
    missing = [c for c in required if c not in input_df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if input_df[required].isna().any().any():
        raise ValueError("Input contains missing feature values.")

    load_env()

    if os.environ.get("QUICKML_ENDPOINT_URL", "").strip():
        if len(input_df) <= 24:
            return quickml_predict(input_df)
        print("Large batch detected; using local model to avoid API timeouts.")

    return local_predict(input_df)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    data = pd.read_csv(args.input)
    predictions = predict(data)

    result = pd.DataFrame({
        "timestamp": data["timestamp"],
        "target_demand_kw": predictions,
    })
    result.to_csv(args.output, index=False)
    print(f"Saved {len(result)} predictions to {args.output}")
    print(result.head().to_string(index=False))
