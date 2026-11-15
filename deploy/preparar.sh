#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

MAREA_HOST="${MANGROOVE_MAREA_HOST:?}"
REGION_DIR="deploy/estero_real"
GMW_URL="https://zenodo.org/records/6894273/files/gmw_v3_2020_gtiff.zip?download=1"
GMW_TILE="gmw_v3_2020/GMW_N13W088_2020_v3.tif"

command -v gdal_translate > /dev/null || {
  echo "Falta gdal_translate: sudo apt install gdal-bin" >&2
  exit 1
}

if [ ! -d "$MAREA_HOST/GOT4.10c/grids_oceantide_netcdf" ]; then
  mkdir -p "$MAREA_HOST"

  docker compose --profile prod run --rm --no-deps -T --user root \
    -v "$MAREA_HOST:/salida" api-prod \
    python -c "from pyTMD.datasets import fetch_gsfc_got; fetch_gsfc_got(model='GOT4.10', directory='/salida', format='netcdf')"
fi

ls "$MAREA_HOST/GOT4.10c/grids_oceantide_netcdf"

if [ ! -f "$REGION_DIR/manglar.tif" ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT

  curl -fSL -o "$TMP/gmw.zip" "$GMW_URL"

  gdal_translate -q -a_nodata none -projwin -87.45 13.0 -87.29 12.87 \
    -co COMPRESS=DEFLATE "/vsizip/$TMP/gmw.zip/$GMW_TILE" "$REGION_DIR/manglar.tif"
fi

gdalinfo "$REGION_DIR/manglar.tif" | grep -E "Size is|NoData" || true
