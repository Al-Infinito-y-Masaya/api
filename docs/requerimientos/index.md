---
icon: lucide/list-checks
---

# Requerimientos

Mangroove convierte las observaciones del radar NISAR en un mapa de conectividad
hidrológica del manglar: qué hectáreas siguen inundándose con la marea y cuáles
quedaron aisladas. Esta versión del documento reemplaza al documento preliminar
de requerimientos de software del 14 de noviembre de 2026 y cambia una decisión
de fondo: **todo el procesamiento ocurre en el backend**. La aplicación web solo
presenta lo que el backend ya calculó.

- **Reglas de negocio:** 18
- **Requerimientos funcionales:** 54, en tres superficies
- **Requerimientos no funcionales:** 16

|             Sección              |                         Contenido                          |
| :------------------------------: | :--------------------------------------------------------: |
|   [Reglas de negocio][reglas]    | Las reglas científicas y de datos que ningún cálculo rompe |
|    [Motor de análisis][motor]    |       Ingesta, procesamiento, métricas y publicación       |
|      [Operación][operacion]      | Lo que hace el equipo de Mangroove desde la API protegida  |
|   [Consulta pública][consulta]   |       Lo que la aplicación web lee de la API pública       |
| [No funcionales][no-funcionales] | Rendimiento, infraestructura, reproducibilidad y apertura  |

---

## Cambios respecto al documento preliminar

!!! abstract "Siete cambios de fondo"

    === "**Backend en lugar de sitio estático**"

        El documento preliminar pedía un sitio estático sin servidor
        (`RNF-11`) y que todo se precalculara en un repositorio. Esta versión
        aloja el motor y una API REST en una instancia EC2. La aplicación web
        sigue siendo estática y se publica aparte; el backend publica además un
        respaldo estático en la CDN para que la app funcione aunque la API no
        responda. Ver [`D-01`][d-01].

    === "**Datos cerca de NASA**"

        La instancia corre en AWS `us-west-2`, la región donde ASF guarda NISAR.
        El motor lee directo de S3 solo la ventana de cada región y guarda en
        disco recortes a resolución nativa, no productos completos de ~6 GB.
        Ver [`D-02`][d-02].

    === "**Varias regiones**"

        El Delta del Estero Real es la primera región, no la única. Cada región
        tiene su polígono, su grilla y su proyección UTM, y se procesa por
        separado. Ver [`RF-O-02`][rf-o-02].

    === "**Madurez y reprocesos**"

        NASA publica productos `PROVISIONAL` y `VALIDATED` con versiones de
        procesamiento (CRID) distintas, y reprocesará las fechas viejas. Ninguna
        corrida mezcla madurezas y todo reproceso reemplaza a su versión
        anterior. Ver [`RN-01`][rn-01] y [`RN-02`][rn-02].

    === "**Geometrías separadas**"

        La serie de una región mezcla varios tracks con ángulos de incidencia
        distintos. Toda comparación en el tiempo se hace dentro del mismo
        track. Ver [`RN-06`][rn-06].

    === "**Corridas versionadas**"

        Cada análisis es una corrida inmutable con su versión, su perfil de
        umbrales y sus insumos. Publicar es declarar cuál corrida es la vigente.
        Ver [`RN-14`][rn-14] y [`RN-15`][rn-15].

    === "**Capas como imágenes, no teselas**"

        Una región de 60 × 40 km a 1 ha es una imagen de 600 × 400 píxeles. Las
        capas se publican como PNG georreferenciados y no como PMTiles.
        Ver [`D-06`][d-06].

---

## Trazabilidad con el documento preliminar

| Preliminar |                Esta versión                 |                       Nota                        |
| :--------: | :-----------------------------------------: | :-----------------------------------------------: |
|  `RF-01`   | [`RF-M-01`][rf-m-01], [`RF-M-02`][rf-m-02]  |             Lectura parcial desde S3              |
|  `RF-02`   | [`RF-M-02`][rf-m-02], [`RF-M-06`][rf-m-06]  |   Recorte nativo y agregación a 1 ha separados    |
|  `RF-03`   | [`RF-M-06`][rf-m-06], [`RF-M-10`][rf-m-10]  | El promedio a 1 ha sustituye al filtro de speckle |
|  `RF-04`   |   [`RF-O-04`][rf-o-04], [`RN-12`][rn-12]    |        La máscara es un insumo versionado         |
|  `RF-05`   |            [`RF-M-11`][rf-m-11]             |           Con la clase `ND` (sin dato)            |
|  `RF-06`   |            [`RF-C-07`][rf-c-07]             |  La serie de clases de la celda ya las contiene   |
|  `RF-07`   |            [`RF-M-07`][rf-m-07]             |    Con nivel `desconocida` cuando no hay marea    |
|  `RF-08`   |            [`RF-M-13`][rf-m-13]             |                                                   |
|  `RF-09`   |            [`RF-M-14`][rf-m-14]             |                                                   |
|  `RF-10`   |            [`RF-M-15`][rf-m-15]             |       Pasa de hoja de ruta a requerimiento        |
|  `RF-11`   |            [`RF-M-16`][rf-m-16]             |                                                   |
|  `RF-12`   |            [`RF-M-09`][rf-m-09]             |                                                   |
|  `RF-13`   |            [`RF-M-12`][rf-m-12]             |       Pasa de hoja de ruta a requerimiento        |
|  `RF-14`   | [`RF-M-19`][rf-m-19] a [`RF-M-21`][rf-m-21] |             API más respaldo estático             |
|  `RF-15`   |            [`RF-M-22`][rf-m-22]             |                                                   |
|  `RF-16`   |            [`RF-C-02`][rf-c-02]             |    El manifiesto trae polígono, centro y zoom     |
|  `RF-17`   | [`RF-M-19`][rf-m-19], [`RF-C-04`][rf-c-04]  |                                                   |
|  `RF-18`   |            [`RF-C-04`][rf-c-04]             |     El deslizador es del frontend; la capa no     |
|  `RF-19`   |            [`RF-C-02`][rf-c-02]             |     El manifiesto trae las fechas y la marea      |
|  `RF-20`   |            [`RF-C-05`][rf-c-05]             |                                                   |
|  `RF-21`   | [`RF-C-07`][rf-c-07], [`RF-C-08`][rf-c-08]  |                                                   |
|  `RF-22`   |            [`RF-C-10`][rf-c-10]             |                                                   |
|  `RF-23`   |            [`RF-C-06`][rf-c-06]             |                Sigue como _podría_                |
|  `RF-24`   |            [`RF-C-09`][rf-c-09]             |                                                   |
|  `RF-25`   |                  Frontend                   |  El relato no tiene datos propios en el backend   |
|  `RF-26`   |            [`RF-C-02`][rf-c-02]             |       Las leyendas viajan en el manifiesto        |
|  `RF-27`   |            [`RF-C-13`][rf-c-13]             |                                                   |
|  `RF-28`   | [`RF-M-20`][rf-m-20], [`RF-C-14`][rf-c-14]  |                                                   |
|  `RF-29`   |                  Frontend                   |        La API devuelve códigos, no textos         |
|  `RF-30`   |            [`RF-C-03`][rf-c-03]             |   Enlaces con versión, por lo tanto permanentes   |
|  `RNF-11`  |   [`RNF-07`][rnf-07], [`RNF-08`][rnf-08]    |    Reemplazado: API en EC2 y respaldo estático    |

[consulta]: funcionales/consulta.md
[d-01]: ../dominio/decisiones.md#d-01
[d-02]: ../dominio/decisiones.md#d-02
[d-06]: ../dominio/decisiones.md#d-06
[motor]: funcionales/motor.md
[no-funcionales]: no-funcionales.md
[operacion]: funcionales/operacion.md
[reglas]: reglas-negocio.md
[rf-c-02]: funcionales/consulta.md#rf-c-02
[rf-c-04]: funcionales/consulta.md#rf-c-04
[rf-c-05]: funcionales/consulta.md#rf-c-05
[rf-c-07]: funcionales/consulta.md#rf-c-07
[rf-c-08]: funcionales/consulta.md#rf-c-08
[rf-c-09]: funcionales/consulta.md#rf-c-09
[rf-c-10]: funcionales/consulta.md#rf-c-10
[rf-c-13]: funcionales/consulta.md#rf-c-13
[rf-c-14]: funcionales/consulta.md#rf-c-14
[rf-c-03]: funcionales/consulta.md#rf-c-03
[rf-c-06]: funcionales/consulta.md#rf-c-06
[rf-m-01]: funcionales/motor.md#rf-m-01
[rf-m-02]: funcionales/motor.md#rf-m-02
[rf-m-06]: funcionales/motor.md#rf-m-06
[rf-m-07]: funcionales/motor.md#rf-m-07
[rf-m-09]: funcionales/motor.md#rf-m-09
[rf-m-10]: funcionales/motor.md#rf-m-10
[rf-m-11]: funcionales/motor.md#rf-m-11
[rf-m-12]: funcionales/motor.md#rf-m-12
[rf-m-13]: funcionales/motor.md#rf-m-13
[rf-m-14]: funcionales/motor.md#rf-m-14
[rf-m-15]: funcionales/motor.md#rf-m-15
[rf-m-16]: funcionales/motor.md#rf-m-16
[rf-m-19]: funcionales/motor.md#rf-m-19
[rf-m-20]: funcionales/motor.md#rf-m-20
[rf-m-21]: funcionales/motor.md#rf-m-21
[rf-m-22]: funcionales/motor.md#rf-m-22
[rf-o-02]: funcionales/operacion.md#rf-o-02
[rf-o-04]: funcionales/operacion.md#rf-o-04
[rn-01]: reglas-negocio.md#rn-01
[rn-02]: reglas-negocio.md#rn-02
[rn-06]: reglas-negocio.md#rn-06
[rn-12]: reglas-negocio.md#rn-12
[rn-14]: reglas-negocio.md#rn-14
[rn-15]: reglas-negocio.md#rn-15
[rnf-07]: no-funcionales.md#rnf-07
[rnf-08]: no-funcionales.md#rnf-08
