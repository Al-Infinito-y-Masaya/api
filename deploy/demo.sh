#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

REGION="${REGION:-estero_real_demo}"
DESDE="${DESDE:-2026-06-17}"
HASTA="${HASTA:-2026-10-23}"
POR="${DJANGO_SUPERUSER_EMAIL:?}"
ENTRADA="/data/entrada/estero_real"

MANGROOVE_CODIGO="$(git rev-parse --short HEAD)"
export MANGROOVE_CODIGO

manage() {
  docker compose --profile prod run --rm -T api-prod python src/manage.py "$@"
}

paso() {
  printf '\n== %s\n' "$1"
}

paso "1/7 región"
manage crearregion --codigo "$REGION" --nombre "Estero Real" \
  --aoi "$ENTRADA/aoi.wkt" --marea -87.33 12.92 --zoom 13

paso "2/7 insumos"
manage cargarinsumo --region "$REGION" --tipo manglar \
  --archivo "$ENTRADA/manglar.tif" --fuente "Global Mangrove Watch v3 (2020)" \
  --fuente-url "https://zenodo.org/records/6894273" --licencia "CC-BY-4.0" \
  --fecha-dato 2020-01-01 --por "$POR"
manage cargarinsumo --region "$REGION" --tipo paises \
  --archivo "$ENTRADA/paises.geojson" --fuente "Mangroove" \
  --licencia "CC-BY-4.0" --por "$POR"

paso "3/7 sincronización"
manage sincronizar --region "$REGION" --desde "$DESDE" --hasta "$HASTA" \
  --por "$POR" --sin-corrida

paso "4/7 corrida"
SALIDA="$(manage crearcorrida --region "$REGION" --madurez provisional --por "$POR")"
echo "$SALIDA"
CORRIDA="$(echo "$SALIDA" | awk '/^Corrida/ {print $2}')"
VERSION="$(echo "$SALIDA" | awk '/^Corrida/ {print $4}' | tr -d ',')"

paso "5/7 cálculo"
manage ejecutarcorrida "$CORRIDA"

paso "6/7 publicación"
manage publicarcorrida "$CORRIDA" --por "$POR"

paso "7/7 relato"
manage proponerrelato "$REGION" "$VERSION" --por "$POR"

printf '\n%s %s publicada.\n' "$REGION" "$VERSION"
