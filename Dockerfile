# NadiNet API (FastAPI) — serves the precomputed results and the human-approved alert path.
# Build from the repo root:  docker build -t nadinet-api .
# Full (not slim) image: rasterio's bundled GDAL needs system libexpat, which slim lacks.
ARG BASE_IMAGE=python:3.11
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    NADINET_ALERT_GATEWAY=console \
    NADINET_STATIC_DATA=/srv/app/public/data
WORKDIR /srv

# Only what the API needs at runtime (rasterio wheels bundle GDAL; no system packages required).
# Behind a TLS-inspecting proxy, pass its CA:  docker build --secret id=ca_bundle,src=/path/ca.pem .
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -f /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi; \
    pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29" "pydantic>=2.6" "httpx>=0.27" \
    "reportlab>=4.1" "matplotlib>=3.8" "pandas>=2.2" "pyarrow>=16" "numpy>=2.0" "scipy>=1.13" \
    "rasterio>=1.4" "shapely>=2.0" "geopandas>=1.0" "pyogrio>=0.9" "pyproj>=3.6" "affine>=2.4" \
    "scikit-image>=0.24" "scikit-learn>=1.5" "lightgbm>=4.3" "requests>=2.31" "pillow>=10"

COPY src ./src
COPY data/demo ./data/demo
COPY data/processed/metrics ./data/processed/metrics
COPY app/public/data ./app/public/data
COPY app/public/voices ./app/public/voices

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
