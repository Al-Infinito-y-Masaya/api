---
icon: lucide/file-json
---

# Contrato de datos

La forma de lo que la API pública devuelve y de lo que el respaldo estático
contiene. Se declara en los esquemas de la API y se publica como esquema
OpenAPI; el esquema JSON del respaldo y los tipos Zod del frontend derivan de él
([`D-15`][d-15]).

## Rutas públicas

Todas las rutas son de solo lectura y no exigen sesión, salvo la exploración,
que es `POST` porque lleva cuerpo. `{v}` es la versión de la corrida.

|                           Ruta                            |                   Respuesta                   |    Requerimiento     |
| :-------------------------------------------------------: | :-------------------------------------------: | :------------------: |
|                      `GET /regiones`                      |         Regiones con versión vigente          | [`RF-C-01`][rf-c-01] |
|               `GET /regiones/{r}/manifest`                |      `307` a la ruta con versión vigente      | [`RF-C-02`][rf-c-02] |
|        `GET /regiones/{r}/versiones/{v}/manifest`         |                 `Manifiesto`                  | [`RF-C-02`][rf-c-02] |
| `GET /regiones/{r}/versiones/{v}/fechas/{f}/capas/{capa}` |   `302` al PNG de la CDN (`rgb`, `clases`)    | [`RF-C-04`][rf-c-04] |
|      `GET /regiones/{r}/versiones/{v}/capas/{capa}`       | `302` al PNG de la CDN (`if_alta`, `if`, ...) | [`RF-C-05`][rf-c-05] |
|   `GET /regiones/{r}/versiones/{v}/fechas/{f}/sensores`   |     Capas auxiliares cercanas a la fecha      | [`RF-C-06`][rf-c-06] |
|       `GET /regiones/{r}/versiones/{v}/celdas/{id}`       |                    `Celda`                    | [`RF-C-07`][rf-c-07] |
|    `GET /regiones/{r}/versiones/{v}/celdas?lon=&lat=`     |                    `Celda`                    | [`RF-C-08`][rf-c-08] |
|         `GET /regiones/{r}/versiones/{v}/resumen`         |    `Resumen` en JSON o CSV según `Accept`     | [`RF-C-09`][rf-c-09] |
|        `GET /regiones/{r}/versiones/{v}/estanques`        |         Estanques con filtros y orden         | [`RF-C-10`][rf-c-10] |
|        `GET /regiones/{r}/versiones/{v}/hipotesis`        |                Pruebas H1 a H3                | [`RF-C-11`][rf-c-11] |
|     `POST /regiones/{r}/versiones/{v}/exploraciones`      |  Capa de conectividad y resumen recalculados  | [`RF-C-12`][rf-c-12] |
|         `GET /regiones/{r}/versiones/{v}/metodo`          |       Fuentes, insumos, perfil y código       | [`RF-C-13`][rf-c-13] |
|        `GET /regiones/{r}/versiones/{v}/descargas`        |     Archivos con tamaño, suma y licencia      | [`RF-C-14`][rf-c-14] |

Una versión retirada responde `410` en todas sus rutas. Las rutas de operación
viven bajo `/operacion/` con la autenticación del template y se documentan en el
esquema OpenAPI que genera la API.

---

## `Manifiesto`

```json
{
  "formato": "mangroove/1",
  "version": "1.3.0",
  "generado": "2026-11-15T06:00:00Z",
  "region": {
    "codigo": "estero_real",
    "nombre": "Delta del Estero Real",
    "bbox": [-87.4, 12.8, -87.05, 13.1],
    "centro": [-87.22, 12.95],
    "zoom_inicial": 11,
    "zona_horaria": "America/Managua",
    "grilla": {
      "epsg": 32616,
      "celda_m": 100,
      "x0": 457200,
      "y0": 1432500,
      "ancho": 380,
      "alto": 330
    }
  },
  "fuente": {
    "mision": "NISAR",
    "producto": "L2 GCOV",
    "madurez": "provisional",
    "crids": ["P05023"]
  },
  "fechas": [
    {
      "id": "2026-10-14_033_asc",
      "fecha_hora": "2026-10-14T11:22:20Z",
      "track": 33,
      "orbita": "asc",
      "crid": "P05023",
      "incidencia": 41.35,
      "cobertura": 1.0,
      "marea_m": 0.81,
      "marea_nivel": "alta",
      "lluvia_3d_mm": 12.4,
      "usada_en_if_alta": true,
      "capas": {
        "rgb": "regiones/estero_real/versiones/1.3.0/fechas/2026-10-14_033_asc/capas/rgb",
        "clases": "regiones/estero_real/versiones/1.3.0/fechas/2026-10-14_033_asc/capas/clases"
      }
    }
  ],
  "brechas": [
    {
      "desde": "2026-07-27T22:03:25Z",
      "hasta": "2026-08-10T00:55:27Z",
      "motivo": "Brecha permanente del instrumento NISAR"
    }
  ],
  "limites": [-87.401, 12.799, -87.049, 13.101],
  "capas": {
    "if_alta": "regiones/estero_real/versiones/1.3.0/capas/if_alta",
    "if": "regiones/estero_real/versiones/1.3.0/capas/if",
    "desconexion": "regiones/estero_real/versiones/1.3.0/capas/desconexion",
    "p_error": "regiones/estero_real/versiones/1.3.0/capas/p_error",
    "cambio": "regiones/estero_real/versiones/1.3.0/capas/cambio",
    "estanques": "regiones/estero_real/versiones/1.3.0/estanques",
    "areas_protegidas": "regiones/estero_real/versiones/1.3.0/descargas/areas_protegidas.geojson"
  },
  "umbrales": {
    "perfil": "predeterminado",
    "version": 1,
    "ow_hh_db": -16.5,
    "ow_hv_db": -22.0,
    "iv_hh_db": -6.5,
    "iv_ratio_db": 5.0,
    "marea_alta_m": 0.55,
    "marea_baja_m": -0.55,
    "lluvia_max_mm": 60,
    "if_alta_desconectada": 0.2,
    "min_fechas_alta": 3,
    "cusum_confianza": 0.95,
    "cusum_perdida_db": 1.5
  },
  "leyendas": {
    "clases": [
      { "codigo": "IV", "color": "#199e70" },
      { "codigo": "OW", "color": "#3987e5" },
      { "codigo": "NI", "color": "#5c5b57" },
      { "codigo": "NC", "color": "#d95926" }
    ]
  },
  "codigo": "a1b2c3d",
  "exploracion": false
}
```

- **`limites`** son las esquinas en lon/lat (oeste, sur, este, norte) de todas
  las capas PNG de la versión: comparten extensión porque comparten grilla.
- **`umbrales`** trae el perfil completo; el ejemplo lo abrevia.
- **`capas`** de cada fecha y de la corrida son rutas relativas a la base de la
  API. En el respaldo estático son rutas relativas a la base de la CDN, con
  extensión.
- **`exploracion`** es verdadero solo en las respuestas de
  [`RF-C-12`][rf-c-12].

## `Celda`

```json
{
  "id": "c_458450_1428650",
  "centroide": [-87.3832, 12.9221],
  "pais": "NI",
  "en_mascara": true,
  "metricas": {
    "if": 0.31,
    "if_alta": 0.05,
    "n_fechas": 26,
    "n_fechas_alta": 7,
    "desconectada": true,
    "datos_suficientes": true,
    "p_error": 0.18,
    "if_esperada": 0.86
  },
  "cambio": {
    "fecha_id": "2026-09-20_033_asc",
    "confianza": 0.97,
    "delta_hv_db": -2.7
  },
  "serie": [
    {
      "fecha_id": "2026-06-28_033_asc",
      "hh_db": -6.1,
      "hv_db": -14.2,
      "coherencia": null,
      "clase": "NI"
    }
  ]
}
```

---

## Reglas del contrato

1. **La marea vive en el manifiesto, no en cada celda.** Cada punto de la serie
   trae `fecha_id` y el frontend lo une con `manifest.fechas`. Así la marea no se
   repite en cientos de miles de celdas.
2. **La serie va en el orden de `manifest.fechas`.** El punto `k` de la serie de
   cualquier celda corresponde a la fecha `k` del manifiesto de su versión.
3. **`null` tiene significado.** `metricas: null` es fuera de la máscara de
   manglar ([`RN-12`][rn-12]); `cambio: null` es sin cambio significativo
   ([`RN-13`][rn-13]); `if_alta: null` es sin datos suficientes
   ([`RN-10`][rn-10]); `marea_m: null` es sin estimación de marea
   ([`RN-08`][rn-08]).
4. **Todo pertenece a una versión.** Una celda, una capa o un resumen se piden
   siempre con la versión del manifiesto que la app tiene cargado.

---

## Razones de la forma

|         Elemento         |                             Forma                             |                       Motivo                        |
| :----------------------: | :-----------------------------------------------------------: | :-------------------------------------------------: |
|  Identificador de fecha  |                     `2026-06-17_033_asc`                      |     Dos tracks pueden compartir órbita y fecha      |
|  Identificador de celda  |                      `c_458450_1428650`                       |                   [`D-03`][d-03]                    |
|         `region`         |                Caja, centro y grilla completa                 |         La app calcula la celda de un clic          |
|         `fuente`         |         `madurez` y `crids`; además, `crid` por fecha         |                  [`RN-01`][rn-01]                   |
| `marea_m`, `marea_nivel` |                Nulo y `desconocida` admitidos                 |                  [`RN-08`][rn-08]                   |
|          Fechas          | Track, CRID, incidencia, cobertura, lluvia y uso en `if_alta` |   La app filtra por geometría y explica `if_alta`   |
|        `brechas`         |                       Lista de brechas                        |                  [`RN-17`][rn-17]                   |
|        `umbrales`        |                Perfil completo con su versión                 |        Reproducibilidad, [`RNF-11`][rnf-11]         |
|          Capas           |                   PNG con `limites` comunes                   |                   [`D-06`][d-06]                    |
|          Celdas          |       Una por petición, por identificador o coordenada        |      [`RF-C-08`][rf-c-08], [`RNF-02`][rnf-02]       |
|        `metricas`        |                     Incluye `if_esperada`                     | Separa manglar alto natural de manglar desconectado |
|        `leyendas`        |                  Códigos y colores por capa                   |             El backend dibuja las capas             |
|   `version`, `codigo`    |   Versión de la corrida y versión del código, por separado    |                  [`RN-15`][rn-15]                   |

[d-03]: decisiones.md#d-03
[d-06]: decisiones.md#d-06
[d-15]: decisiones.md#d-15
[rf-c-01]: ../requerimientos/funcionales/consulta.md#rf-c-01
[rf-c-02]: ../requerimientos/funcionales/consulta.md#rf-c-02
[rf-c-04]: ../requerimientos/funcionales/consulta.md#rf-c-04
[rf-c-05]: ../requerimientos/funcionales/consulta.md#rf-c-05
[rf-c-06]: ../requerimientos/funcionales/consulta.md#rf-c-06
[rf-c-07]: ../requerimientos/funcionales/consulta.md#rf-c-07
[rf-c-08]: ../requerimientos/funcionales/consulta.md#rf-c-08
[rf-c-09]: ../requerimientos/funcionales/consulta.md#rf-c-09
[rf-c-10]: ../requerimientos/funcionales/consulta.md#rf-c-10
[rf-c-11]: ../requerimientos/funcionales/consulta.md#rf-c-11
[rf-c-12]: ../requerimientos/funcionales/consulta.md#rf-c-12
[rf-c-13]: ../requerimientos/funcionales/consulta.md#rf-c-13
[rf-c-14]: ../requerimientos/funcionales/consulta.md#rf-c-14
[rn-01]: ../requerimientos/reglas-negocio.md#rn-01
[rn-08]: ../requerimientos/reglas-negocio.md#rn-08
[rn-10]: ../requerimientos/reglas-negocio.md#rn-10
[rn-12]: ../requerimientos/reglas-negocio.md#rn-12
[rn-13]: ../requerimientos/reglas-negocio.md#rn-13
[rn-15]: ../requerimientos/reglas-negocio.md#rn-15
[rn-17]: ../requerimientos/reglas-negocio.md#rn-17
[rnf-02]: ../requerimientos/no-funcionales.md#rnf-02
[rnf-11]: ../requerimientos/no-funcionales.md#rnf-11
