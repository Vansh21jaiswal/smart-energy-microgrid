"""Entry-point shim used by some Catalyst AppSail configurations."""
from main import app  # noqa: F401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
