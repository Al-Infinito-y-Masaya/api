---
icon: lucide/map
---

# Consulta pública

- **Módulos:** 4
- **Total:** 11

Los flujos describen lo que hace el backend. Lo que la app dibuja con esas
respuestas (el relato guiado, la animación, el deslizador) es del frontend.

---

## Exploración

### CU-C-01

> **Abrir la app en una región**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** La región tiene al menos una corrida publicada
- **Requerimientos:**
  > - [`RF-C-01`][rf-c-01]
  > - [`RF-C-02`][rf-c-02]
  > - [`RF-C-15`][rf-c-15]

**Flujo principal**

1. La app pide el listado de regiones.
2. El sistema devuelve las regiones activas con su versión vigente.
3. La app pide el manifiesto vigente de la región elegida.
4. El sistema redirige a la ruta con versión.
5. La app pide el manifiesto con versión y el sistema lo devuelve desde caché.

!!! example "**Alternativas**"

    === "**3a**"

        **El enlace ya trae una versión**

        La app pide directamente el manifiesto con versión y se salta la
        redirección.

    === "**4a**"

        **La región no tiene corrida publicada**

        El sistema responde `404` y la región no figuraba en el listado.

- **Postcondición:** La app conoce la grilla, las fechas, las capas y los umbrales de la versión.

### CU-C-02

> **Recorrer el ritmo del manglar**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-02`][rf-c-02]
  > - [`RF-C-04`][rf-c-04]

**Flujo principal**

1. La persona elige una fecha en la línea de tiempo; la app marca su marea.
2. La app pide el compuesto RGB de esa fecha.
3. El sistema redirige al PNG de la CDN, con sus esquinas declaradas en el manifiesto.
4. La persona pulsa _Reproducir_ y la app pide el mapa de clases de cada fecha en orden.
5. Para comparar dos fechas, la app pide la capa de cada una y las muestra a los lados del deslizador.

!!! example "**Alternativas**"

    === "**1a**"

        **La fecha cae en una brecha de datos**

        El manifiesto declara la brecha; la línea de tiempo la muestra como
        _sin dato_ y la animación la salta.

    === "**4a**"

        **Las fechas mezclan tracks**

        El manifiesto trae el track y la órbita de cada fecha; la app puede
        filtrar por órbita para no comparar geometrías distintas.

- **Postcondición:** La persona identifica zonas que se inundan y se secan con la marea.

---

## Conectividad

### CU-C-03

> **Identificar manglar desconectado**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-05`][rf-c-05]
  > - [`RF-C-09`][rf-c-09]

**Flujo principal**

1. La persona abre la vista de conectividad.
2. La app pide la capa de `if_alta` y la de manglar desconectado.
3. La persona elige un país.
4. La app pide el resumen y muestra las hectáreas desconectadas y su porcentaje del manglar del país.
5. La persona hace clic en un parche y sigue en [`CU-C-04`](#cu-c-04).

!!! example "**Alternativas**"

    === "**2a**"

        **La versión no tiene marea**

        El manifiesto declara las fechas con nivel `desconocida`; la capa de
        `if_alta` no existe y la app muestra la de `if` con la advertencia de
        que no separa la marea.

    === "**4a**"

        **Celdas con datos insuficientes**

        El resumen las cuenta aparte y la capa las muestra con trama, por
        [`RN-10`][rn-10].

- **Postcondición:** La persona tiene una lista de zonas candidatas a verificar en campo.

### CU-C-04

> **Inspeccionar una celda**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-07`][rf-c-07]
  > - [`RF-C-08`][rf-c-08]

**Flujo principal**

1. La persona hace clic en el mapa.
2. La app pide la celda que contiene esa longitud y latitud en la versión cargada.
3. El sistema calcula la fila y la columna, lee la fila de resultados y devuelve la celda.
4. La app une la serie con la marea del manifiesto y dibuja HH, HV y marea en el tiempo, la banda de clases, las métricas y el cambio.

!!! example "**Alternativas**"

    === "**3a**"

        **El punto cae fuera de la grilla**

        El sistema responde `404` con el motivo y la app no abre el panel.

    === "**3b**"

        **La celda está fuera de la máscara de manglar**

        El sistema devuelve la serie con las métricas y el cambio nulos, por
        [`RN-12`][rn-12]; la app lo indica.

    === "**3c**"

        **La celda no tiene cambio significativo**

        El cambio llega nulo y la app no marca fecha de deterioro.

- **Postcondición:** La persona puede justificar o cuestionar el estado de esa celda.

### CU-C-05

> **Explorar con otros umbrales**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-12`][rf-c-12]

**Flujo principal**

1. La persona elige otro perfil o mueve un umbral en el panel de método.
2. La app envía los umbrales para la versión cargada.
3. El sistema valida los rangos, calcula la huella de los umbrales y busca el resultado en caché.
4. Si no está, recalcula clases, desconexión y resumen sobre las grillas de la versión y lo guarda en caché.
5. El sistema devuelve la capa de conectividad y el resumen, marcados como exploración.

!!! example "**Alternativas**"

    === "**3a**"

        **Un umbral fuera de rango**

        El sistema responde `422` señalando el campo.

    === "**4a**"

        **Se agotó el límite de exploraciones de esa IP**

        El sistema responde `429` con el tiempo de espera; los perfiles
        publicados siguen disponibles sin límite propio.

- **Postcondición:** La persona ve cuánto cambia el mapa con criterios distintos, sin alterar la versión publicada.

---

## Estanques

### CU-C-06

> **Priorizar estanques para restauración**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** La versión tiene estanques
- **Requerimientos:**
  > - [`RF-C-10`][rf-c-10]

**Flujo principal**

1. La persona abre la vista de estanques y filtra por abandonados.
2. La app pide el listado ordenado por puntaje.
3. La persona cambia el orden a área, distancia al canal o inundación del manglar vecino.
4. Selecciona un estanque; la app lo resalta con su polígono.

!!! example "**Alternativas**"

    === "**1a**"

        **La región no tiene estanques digitalizados**

        El manifiesto no declara la capa y la app no muestra la vista.

- **Postcondición:** La persona tiene una lista priorizada de sitios.

---

## Método y datos

### CU-C-07

> **Revisar el método, las fuentes y las hipótesis**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-11`][rf-c-11]
  > - [`RF-C-13`][rf-c-13]

**Flujo principal**

1. La persona abre _Método y datos_.
2. La app pide el método de la versión: gránulos, CRID, madurez, insumos, licencias, perfil, modelo de marea y versión del código.
3. La app pide las pruebas de hipótesis y muestra cada una con sus grupos, su valor p y su tamaño de efecto.

!!! example "**Alternativas**"

    === "**3a**"

        **Una prueba no fue evaluable**

        El sistema la devuelve con su motivo (menos de cinco celdas por grupo,
        falta de bordas digitalizadas) en lugar de omitirla.

- **Postcondición:** La persona sabe de dónde sale cada dato y cómo regenerarlo.

### CU-C-08

> **Descargar datos**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-14`][rf-c-14]

**Flujo principal**

1. La persona abre las descargas de la versión.
2. El sistema lista los archivos con tamaño, suma y licencia.
3. La persona elige uno y la app la lleva a la CDN.

- **Postcondición:** La persona puede abrir los datos en QGIS u otra herramienta.

### CU-C-09

> **Compartir una vista**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Manifiesto cargado
- **Requerimientos:**
  > - [`RF-C-03`][rf-c-03]

**Flujo principal**

1. La persona pulsa _Compartir_.
2. La app arma un enlace con la región, la versión, la capa, la fecha y el zoom.
3. Quien abre el enlace sigue [`CU-C-01`](#cu-c-01) por la alternativa **3a**.

!!! example "**Alternativas**"

    === "**3a**"

        **La versión del enlace fue retirada**

        El sistema responde `410` y la app ofrece abrir la versión vigente.

- **Postcondición:** Quien recibe el enlace ve exactamente la misma vista.

### CU-C-10

> **Comparar sensores**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** La región tiene capas auxiliares de otros sensores
- **Requerimientos:**
  > - [`RF-C-06`][rf-c-06]

**Flujo principal**

1. La persona abre el comparador y elige una fecha de NISAR.
2. La app pide las capas auxiliares más cercanas de un sensor óptico y uno de banda C.
3. El sistema las devuelve con su fecha, su distancia en días y, en la óptica, su porcentaje de nubes.
4. La persona elige dos fuentes y arrastra el deslizador.

!!! example "**Alternativas**"

    === "**3a**"

        **No hay escena óptica sin nubes cerca**

        El sistema devuelve la más cercana con su porcentaje de nubes. Ese vacío
        ilustra la ventaja del radar en la temporada de lluvias.

- **Postcondición:** La persona entiende que solo la banda L ve el agua bajo los árboles.

### CU-C-11

> **Usar la app con la API caída**

- **Actor:** [Visitante][act-visitante]
- **Precondición:** Hay al menos una corrida publicada con respaldo estático
- **Requerimientos:**
  > - [`RF-C-02`][rf-c-02]
  > - [`RF-M-21`][rf-m-21]

**Flujo principal**

1. La app no recibe respuesta de la API al pedir el listado de regiones.
2. La app lee el respaldo estático de la CDN, con la misma forma del contrato.
3. Muestra mapas, línea de tiempo, conectividad y resumen, y avisa que el inspector de celdas y la exploración no están disponibles.

- **Postcondición:** La persona sigue viendo los resultados de la última versión publicada.

[act-visitante]: ../actores/consulta.md#visitante
[rf-c-01]: ../requerimientos/funcionales/consulta.md#rf-c-01
[rf-c-02]: ../requerimientos/funcionales/consulta.md#rf-c-02
[rf-c-03]: ../requerimientos/funcionales/consulta.md#rf-c-03
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
[rf-c-15]: ../requerimientos/funcionales/consulta.md#rf-c-15
[rf-m-21]: ../requerimientos/funcionales/motor.md#rf-m-21
[rn-10]: ../requerimientos/reglas-negocio.md#rn-10
[rn-12]: ../requerimientos/reglas-negocio.md#rn-12
