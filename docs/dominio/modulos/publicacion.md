---
icon: lucide/upload-cloud
---

# Publicación

Una tabla en la app `mangroove_publicacion`: los archivos que una corrida deja
en la CDN. La exploración de umbrales no tiene tabla, por [`D-07`][d-07].

## Requerimientos cubiertos

- [`RF-M-19`][rf-m-19] a [`RF-M-21`][rf-m-21]
- [`RF-C-04`][rf-c-04]
- [`RF-C-05`][rf-c-05]
- [`RF-C-14`][rf-c-14]

---

## `Artefacto`

Un archivo publicado de una corrida: una capa, una descarga o una pieza del
respaldo estático.

- **Régimen:** [Resultado de corrida][regimenes]
- **Volumen estimado:** unas 80 filas por corrida de 31 fechas
- **Origen:**
  > - [`RF-M-19`][rf-m-19]
  > - [`RF-M-20`][rf-m-20]
  > - [`RF-M-21`][rf-m-21]

### Columnas

|              Campo              |     Tipo      | Nulo | Predeterminado |                            Descripción                            |
| :-----------------------------: | :-----------: | :--: | :------------: | :---------------------------------------------------------------: |
|          `corrida_id`           |    `uuid`     |  no  |                |                                                                   |
|       `corrida_fecha_id`        |    `uuid`     |  sí  |                |     Fecha de la capa; nulo en capas y archivos de la corrida      |
|             `tipo`              | `varchar(30)` |  no  |                |                  Ver la tabla de tipos de abajo                   |
|            `formato`            | `varchar(8)`  |  no  |                |            `png` / `tif` / `csv` / `json` / `geojson`             |
|           `media_id`            |    `uuid`     |  no  |                |  Archivo en Bunny, visibilidad pública (`ApiMedia` del template)  |
|            `sha256`             |  `char(64)`   |  no  |                |                                                                   |
|             `bytes`             |   `bigint`    |  no  |                |                                                                   |
| `oeste`, `sur`, `este`, `norte` |   `float8`    |  sí  |                | Esquinas en lon/lat de las capas PNG; nulas en los demás formatos |

### Tipos de artefacto

|       Tipo       |   Por fecha   |  Formato  |                          Contenido                           |
| :--------------: | :-----------: | :-------: | :----------------------------------------------------------: |
|      `rgb`       |      sí       |   `png`   |                 R = HH, G = HV, B = HH − HV                  |
|     `clases`     |      sí       |   `png`   |          `IV`, `OW`, `NI`, `NC`; `ND` transparente           |
|    `if_alta`     |      no       |   `png`   |        Rampa secuencial; trama sin datos suficientes         |
|       `if`       |      no       |   `png`   |                       Rampa secuencial                       |
|  `desconexion`   |      no       |   `png`   |   Desconectado, conectado y datos insuficientes con trama    |
|    `p_error`     |      no       |   `png`   |                       Rampa secuencial                       |
|     `cambio`     |      no       |   `png`   |          Delta de HV de los cambios significativos           |
| `geotiff_<capa>` | según la capa |   `tif`   | La capa con valores numéricos, en la proyección de la región |
|  `resumen_csv`   |      no       |   `csv`   |                 Resumen por país y por fecha                 |
|   `estanques`    |      no       | `geojson` |          Estanques con su clase, su CV y su puntaje          |
|   `metadatos`    |      no       |  `json`   | Gránulos, insumos, perfil, código y licencias de la corrida  |
|   `manifiesto`   |      no       |  `json`   |         El manifiesto del contrato, para el respaldo         |
|    `resumen`     |      no       |  `json`   |          El resumen del contrato, para el respaldo           |

### Constraints

```postgresql
CONSTRAINT chk_artefacto_esquinas
CHECK (
  (formato = 'png') = (oeste IS NOT NULL AND sur IS NOT NULL AND este IS NOT NULL AND norte IS NOT NULL)
)

CONSTRAINT chk_artefacto_por_fecha
CHECK ((tipo IN ('rgb', 'clases')) = (corrida_fecha_id IS NOT NULL))
```

### Unicidad

|               Nombre               |                        Definición                         |
| :--------------------------------: | :-------------------------------------------------------: |
| `unq_artefacto_corrida_tipo_fecha` | `(corrida_id, tipo, corrida_fecha_id) NULLS NOT DISTINCT` |

### Ruta en la CDN

Cada artefacto se sube a una ruta que incluye la región y la versión:
`/<region>/<version>/<tipo>[/<fecha_id>].<formato>`. Como ningún artefacto de
una versión cambia, la CDN los sirve con caché inmutable. El respaldo estático
es el mismo conjunto de archivos, más `/<region>/vigente.json`, el único
archivo que se sobrescribe, que apunta a la versión vigente.

La purga de una corrida retirada borra sus filas de `Artefacto` y los objetos
correspondientes en Bunny. Las filas de `ApiMedia` no se borran, por el régimen
protegido del template: quedan como huella de lo que se publicó, con su suma y
su tamaño, aunque el archivo ya no exista.

[d-07]: ../decisiones.md#d-07
[regimenes]: ../convenciones.md#regimenes-de-escritura
[rf-c-04]: ../../requerimientos/funcionales/consulta.md#rf-c-04
[rf-c-05]: ../../requerimientos/funcionales/consulta.md#rf-c-05
[rf-c-14]: ../../requerimientos/funcionales/consulta.md#rf-c-14
[rf-m-19]: ../../requerimientos/funcionales/motor.md#rf-m-19
[rf-m-20]: ../../requerimientos/funcionales/motor.md#rf-m-20
[rf-m-21]: ../../requerimientos/funcionales/motor.md#rf-m-21
