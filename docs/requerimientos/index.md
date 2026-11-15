---
icon: lucide/list-checks
---

# Requerimientos

Mangroove convierte las observaciones del radar NISAR en un mapa de conectividad
hidrológica del manglar: qué hectáreas siguen inundándose con la marea y cuáles
quedaron aisladas. **Todo el procesamiento ocurre en el backend**; la aplicación
web solo presenta lo que el backend ya calculó.

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

## Principios

!!! abstract "Siete principios que ordenan los requerimientos"

    === "**El backend calcula**"

        El motor y una API REST corren en una instancia EC2. La aplicación web
        es un sitio estático publicado aparte, que no calcula nada. El backend
        publica además un respaldo estático en la CDN para que la app funcione
        aunque la API no responda. Ver [`D-01`][d-01].

    === "**Datos cerca de NASA**"

        La instancia corre en AWS `us-west-2`, la región donde ASF guarda NISAR.
        El motor lee directo de S3 solo la ventana de cada región y guarda en
        disco recortes a resolución nativa, nunca productos completos de ~6 GB.
        Ver [`D-02`][d-02].

    === "**Varias regiones**"

        El Delta del Estero Real es la primera región, no la única. Cada región
        tiene su polígono, su grilla y su proyección UTM, y se procesa por
        separado. Ver [`RF-O-02`][rf-o-02].

    === "**Madurez y reprocesos**"

        NASA publica productos `PROVISIONAL` y `VALIDATED` con versiones de
        procesamiento (CRID) distintas, y reprocesa las fechas viejas. Ninguna
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

    === "**Capas como imágenes**"

        Una región de 60 × 40 km a 1 ha es una imagen de 600 × 400 píxeles. Las
        capas se publican como PNG georreferenciados, sin pirámide de teselas.
        Ver [`D-06`][d-06].

---

## Alcance de la aplicación web

El backend no cubre lo que la aplicación web resuelve por sí sola: el relato
guiado, la animación de la línea de tiempo, el deslizador entre dos fechas y los
textos en español e inglés. La API devuelve códigos y datos; cada leyenda trae
códigos y colores, y la app pone las palabras.

[consulta]: funcionales/consulta.md
[d-01]: ../dominio/decisiones.md#d-01
[d-02]: ../dominio/decisiones.md#d-02
[d-06]: ../dominio/decisiones.md#d-06
[motor]: funcionales/motor.md
[no-funcionales]: no-funcionales.md
[operacion]: funcionales/operacion.md
[reglas]: reglas-negocio.md
[rf-o-02]: funcionales/operacion.md#rf-o-02
[rn-01]: reglas-negocio.md#rn-01
[rn-02]: reglas-negocio.md#rn-02
[rn-06]: reglas-negocio.md#rn-06
[rn-14]: reglas-negocio.md#rn-14
[rn-15]: reglas-negocio.md#rn-15
