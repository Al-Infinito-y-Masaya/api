---
icon: lucide/ruler
---

# Convenciones

Las convenciones de nomenclatura, llaves y nulabilidad son las del template y de
los proyectos que lo usan. Esta página fija lo que es propio del dominio: los
tipos de los datos de radar, los regímenes de escritura y la codificación de
las series.

## Tipos de dato canónicos

|          Concepto          |      Tipo      |                          Regla                          |
| :------------------------: | :------------: | :-----------------------------------------------------: |
|       Llave primaria       |     `uuid`     |           `uuidv7()`, heredada de `ApiModel`            |
|          Instante          | `timestamptz`  |                       Siempre UTC                       |
|    Fecha de calendario     |     `date`     |  En la zona horaria de la región, por [`RN-18`][rn-18]  |
|     Coordenada lon/lat     |    `float8`    |                 WGS84, `CHECK` de rango                 |
|   Coordenada proyectada    |    `float8`    |             Metros en el EPSG de la región              |
|        Código EPSG         |   `integer`    |     `CHECK` de zona UTM (32601-32660, 32701-32760)      |
|   Decibeles en una serie   |  `smallint[]`  |    dB × 100; `-32768` = sin dato, por [`D-04`][d-04]    |
|    Decibeles escalares     |     `real`     |               Desfases, deltas y umbrales               |
|          Fracción          |     `real`     |                   `CHECK` entre 0 y 1                   |
|      Altura de marea       |     `real`     | Metros respecto al nivel medio; `NULL` = sin estimación |
|      Clase por fecha       |  `smallint[]`  |  Códigos de la tabla de clases, alineados con la serie  |
|    Track, frame, ciclo     |   `smallint`   |                Tal como los numera NISAR                |
|            CRID            |  `varchar(6)`  |                  Patrón `^P[0-9]{5}$`                   |
|   Identificador de celda   | `varchar(24)`  |            `c_<E>_<N>`, por [`RN-04`][rn-04]            |
|   Identificador de fecha   | `varchar(20)`  |          `AAAA-MM-DD_TTT_orbita`, en fecha UTC          |
|      Versión de datos      | `varchar(20)`  |            Semver, patrón `^\d+\.\d+\.\d+$`             |
|      Suma de archivo       |   `char(64)`   |   SHA-256 en hexadecimal; `''` = sin archivo todavía    |
|   Ruta de archivo local    | `varchar(255)` |    Relativa a `MANGROOVE_DATOS`, por [`D-09`][d-09]     |
| Código estable de catálogo | `varchar(50)`  |               Patrón `^[a-z][a-z0-9_]*$`                |
|       Lista cerrada        |  `varchar(n)`  |             `CHECK` contra un `TextChoices`             |
|            País            |  `varchar(2)`  | ISO 3166-1 alfa-2; `''` = sin asignar o región completa |
|         Geometría          |    `jsonb`     |         GeoJSON en lon/lat, por [`D-08`][d-08]          |

### Códigos de clase

| Código | Clase |                 Significado                 |
| :----: | :---: | :-----------------------------------------: |
|  `0`   | `NI`  |                 No inundado                 |
|  `1`   | `IV`  |             Vegetación inundada             |
|  `2`   | `OW`  |                Agua abierta                 |
|  `3`   | `NC`  |               No clasificado                |
|  `4`   | `ND`  | Sin dato en esa fecha, por [`RN-07`][rn-07] |

La API traduce los códigos a las letras del contrato. En la base son números
porque un arreglo de `smallint` ocupa dos bytes por fecha y se compara sin
cotejamiento.

### _¿Por qué decibeles enteros?_

Dos bytes por valor alcanzan: 0,01 dB de precisión frente a un speckle de
0,9 dB. Un `real`
duplicaría el tamaño de cada fila de resultados sin cambiar ninguna clase.

---

## Regímenes de escritura

Cada tabla hereda de una de las clases base del template, y esa elección decide
qué escrituras admite la base. La ficha de cada tabla declara su régimen.

|         Régimen          |                Clase base                |                            Admite                            |                     Uso en el dominio                      |
| :----------------------: | :--------------------------------------: | :----------------------------------------------------------: | :--------------------------------------------------------: |
|  **Mutable rastreada**   | `ApiProtectedModel` con `track_table()`  |         Inserción y edición auditada; nunca borrado          | Entidades con estado: `Recorte`, `Adquisicion`, `Corrida`  |
|    **Borrado lógico**    | `ApiSoftDeleteModel` con `track_table()` |        `DELETE` se reescribe como `is_active = false`        |                          `Region`                          |
|    **Solo inserción**    |           `ApiAppendOnlyModel`           |             Inserción; la base rechaza el resto              | Hechos y versiones: `Producto`, `Insumo`, `PerfilUmbrales` |
| **Resultado de corrida** |    `ApiAppendOnlyModel` con excepción    | Inserción; borrado solo por la purga de una corrida retirada |  `CorridaFecha`, `ResultadoCelda`, resúmenes, artefactos   |

### _¿Por qué un régimen propio para los resultados?_

Los resultados son tan inmutables como un hecho, pero una corrida retirada no
puede ocupar 230 000 filas para siempre. El régimen reemplaza el
`trg_append_only` heredado por `trg_resultado_solo_insercion`: rechaza toda
actualización y solo admite el borrado cuando la corrida de la fila está
retirada y su `purgar_despues_de` ya pasó. Es la misma garantía, con una única
puerta de salida que no depende de quién escriba.

---

## Nomenclatura y nulabilidad

Se aplican sin cambios las del template:

- **Restricciones con nombre explícito:** `unq_`, `chk_`, `excl_`, `idx_`,
  `trg_`, seguidos del nombre de la clase en minúsculas (`%(class)s`).
- **Booleanos nunca nulos.** Un tercer estado es una lista cerrada.
- **Texto y colecciones nunca nulos.** La ausencia es `''` o `'{}'`.
- **`NULL` es la ausencia en números, fechas y llaves.** Cada ficha dice si el
  nulo significa _todavía no_ o _no aplica_.

En este dominio, el nulo numérico tiene un significado científico preciso:
`if_alta` nulo no es cero, es _no hay fechas suficientes para saberlo_. Por eso
los `CHECK` de [`RN-10`][rn-10] a [`RN-13`][rn-13] atan cada nulo a su motivo.

[d-04]: decisiones.md#d-04
[d-08]: decisiones.md#d-08
[d-09]: decisiones.md#d-09
[rn-04]: ../requerimientos/reglas-negocio.md#rn-04
[rn-07]: ../requerimientos/reglas-negocio.md#rn-07
[rn-10]: ../requerimientos/reglas-negocio.md#rn-10
[rn-13]: ../requerimientos/reglas-negocio.md#rn-13
[rn-18]: ../requerimientos/reglas-negocio.md#rn-18
