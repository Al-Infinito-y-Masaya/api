---
icon: lucide/folder-lock
---

# Operación

- **Módulos:** 4
- **Total:** 14

---

## Acceso

### CU-O-01

> **Iniciar sesión de operación**

- **Actor:** [Operador][act-operador]
- **Precondición:** La cuenta de operación está activa y tiene segundo factor
- **Requerimientos:**
  > - [`RF-O-01`][rf-o-01]

**Flujo principal**

1. El operador envía correo y contraseña.
2. El sistema responde con un desafío de segundo factor.
3. El operador envía el código.
4. El sistema emite el JWT con el rol de la cuenta.

!!! example "**Alternativas**"

    === "**4a**"

        **La cuenta no tiene rol de operación**

        El sistema emite la sesión, pero toda ruta de operación responde `403`.

- **Postcondición:** Sesión de operación activa.

### CU-O-02

> **Crear una cuenta de operación**

- **Actor:** [Administrador][act-admin]
- **Precondición:** Sesión de administrador
- **Requerimientos:**
  > - [`RF-O-01`][rf-o-01]
  > - [`RF-O-15`][rf-o-15]

**Flujo principal**

1. El administrador crea la cuenta con el correo y el rol de personal.
2. El sistema envía la verificación de correo.
3. La persona invitada verifica el correo y configura el segundo factor.

!!! example "**Alternativas**"

    === "**1a**"

        **El administrador intenta suspender la última cuenta de administrador**

        El sistema lo rechaza.

- **Postcondición:** Existe una cuenta de operación más, registrada en la bitácora.

---

## Regiones e insumos

### CU-O-03

> **Registrar una región**

- **Actor:** [Operador][act-operador]
- **Precondición:** Sesión de operación
- **Requerimientos:**
  > - [`RF-O-02`][rf-o-02]

**Flujo principal**

1. El operador envía código, nombre, polígono, zona horaria y punto de referencia de marea.
2. El sistema valida el polígono y elige la zona UTM de su centroide.
3. Calcula la grilla: origen, ancho y alto en celdas del tamaño pedido.
4. Crea las celdas con su identificador y su centroide en lon/lat.
5. Devuelve la región con su EPSG, su grilla y su número de celdas.

!!! example "**Alternativas**"

    === "**2a**"

        **El polígono no es válido o tiene lon/lat invertidos**

        El sistema responde `422` con el motivo.

    === "**3a**"

        **La grilla supera el millón de celdas**

        El sistema la rechaza por [`RNF-04`][rnf-04] y sugiere un tamaño de celda
        mayor o un polígono menor.

- **Postcondición:** La región existe, activa para sincronizar y con su grilla congelada. No aparece en el listado público hasta su primera corrida publicada.

### CU-O-04

> **Cargar un insumo auxiliar**

- **Actor:** [Operador][act-operador]
- **Precondición:** La región existe
- **Requerimientos:**
  > - [`RF-O-04`][rf-o-04]

**Flujo principal**

1. El operador sube el archivo con su tipo, su fuente y su licencia.
2. El sistema guarda el archivo en almacenamiento privado y calcula su suma.
3. Rasteriza o reproyecta el insumo a la grilla de la región.
4. Lo registra como la versión siguiente de ese tipo de insumo.

!!! example "**Alternativas**"

    === "**3a**"

        **El archivo no cubre la región**

        El sistema lo rechaza indicando qué fracción de la grilla cubre.

    === "**4a**"

        **El archivo es idéntico a la versión vigente**

        El sistema no crea una versión nueva y devuelve la existente.

- **Postcondición:** Las corridas nuevas usan esta versión; las anteriores conservan la suya.

---

## Datos

### CU-O-05

> **Sincronizar una región**

- **Actor:** [Operador][act-operador] o [Proceso programado][act-proceso]
- **Precondición:** La región está activa y el token de Earthdata está vigente
- **Requerimientos:**
  > - [`RF-O-08`][rf-o-08]
  > - [`RF-M-01`][rf-m-01] a [`RF-M-07`][rf-m-07]
  > - [`RF-M-24`][rf-m-24]

**Flujo principal**

1. El sistema toma el candado de sincronización de la región.
2. Busca productos GCOV en ASF y registra los nuevos.
3. Por cada producto nuevo, lee de S3 la ventana de la región y guarda el recorte.
4. Consolida los recortes en adquisiciones y aplica los reprocesos.
5. Agrega cada adquisición nueva a la grilla y estima su marea.
6. Registra la sincronización con sus conteos y libera el candado.

!!! example "**Alternativas**"

    === "**1a**"

        **Ya hay una sincronización en curso**

        El sistema rechaza la petición manual con `409`; el proceso programado
        simplemente se salta la corrida.

    === "**3a**"

        **Falla la lectura de un producto**

        El producto queda fallido con su error y el lote sigue. Se reintenta en
        la siguiente sincronización, hasta tres veces.

    === "**3b**"

        **El disco no tiene espacio para el recorte**

        El sistema detiene el lote, registra el motivo y avisa al operador.

    === "**4a**"

        **El producto tiene un CRID igual o más viejo que la adquisición vigente**

        Se registra como descartado, con el motivo.

- **Postcondición:** Las adquisiciones nuevas están agregadas y listas para entrar a una corrida.

### CU-O-06

> **Revisar y excluir adquisiciones**

- **Actor:** [Operador][act-operador]
- **Precondición:** La región tiene adquisiciones
- **Requerimientos:**
  > - [`RF-O-05`][rf-o-05]
  > - [`RF-O-06`][rf-o-06]

**Flujo principal**

1. El operador lista las adquisiciones filtradas por madurez y track.
2. Revisa cobertura, incidencia y marea de cada una.
3. Excluye una adquisición con su motivo.

!!! example "**Alternativas**"

    === "**3a**"

        **La exclusión fue un error**

        El operador restituye la adquisición con otro motivo; ambas acciones
        quedan en la bitácora.

- **Postcondición:** Las corridas nuevas no incluyen la adquisición excluida.

### CU-O-07

> **Cargar marea o lluvia**

- **Actor:** [Operador][act-operador]
- **Precondición:** La región existe
- **Requerimientos:**
  > - [`RF-O-07`][rf-o-07]
  > - [`RF-M-07`][rf-m-07]
  > - [`RF-M-08`][rf-m-08]

**Flujo principal**

1. El operador sube el CSV con su tipo (marea o lluvia) y su fuente.
2. El sistema valida el formato, las unidades y que las fechas estén en orden.
3. Para la marea, interpola la serie al instante de cada adquisición y la guarda como otro modelo.
4. Para la lluvia, guarda los valores diarios en la fecha local de la región.

!!! example "**Alternativas**"

    === "**3a**"

        **Una adquisición queda fuera del rango de la serie**

        Esa adquisición queda sin marea de este modelo; no se extrapola.

- **Postcondición:** Una corrida puede elegir la serie cargada.

---

## Análisis

### CU-O-08

> **Crear una versión de un perfil de umbrales**

- **Actor:** [Operador][act-operador]
- **Precondición:** Sesión de operación
- **Requerimientos:**
  > - [`RF-O-09`][rf-o-09]

**Flujo principal**

1. El operador envía el perfil con todos sus umbrales.
2. El sistema valida rangos y coherencia (por ejemplo, marea baja menor que marea alta).
3. Crea la versión siguiente del perfil.

- **Postcondición:** La versión nueva está disponible para corridas y exploraciones; las anteriores no cambian.

### CU-O-09

> **Lanzar una corrida**

- **Actor:** [Operador][act-operador]
- **Precondición:** La región tiene adquisiciones vigentes de la madurez elegida
- **Requerimientos:**
  > - [`RF-O-10`][rf-o-10]
  > - [`RF-M-10`][rf-m-10] a [`RF-M-18`][rf-m-18]

**Flujo principal**

1. El operador elige madurez, versión de perfil, modelo de marea y tracks.
2. El sistema fija la lista de adquisiciones y las versiones de los insumos, y propone la versión semántica.
3. Encola la corrida y responde `202`.
4. El trabajador calibra por track, clasifica, mide, detecta cambios, evalúa hipótesis y resume.
5. Guarda los resultados y deja la corrida completada.

!!! example "**Alternativas**"

    === "**2a**"

        **No hay suficientes fechas de marea alta**

        El sistema crea la corrida igual y lo advierte: las celdas quedarán con
        datos insuficientes, por [`RN-10`][rn-10].

    === "**4a**"

        **El cálculo falla**

        La corrida queda fallida con su error; no deja resultados parciales.

- **Postcondición:** Una corrida completada lista para revisión.

### CU-O-10

> **Revisar y publicar una corrida**

- **Actor:** [Operador][act-operador]
- **Precondición:** La corrida está completada
- **Requerimientos:**
  > - [`RF-O-11`][rf-o-11]
  > - [`RF-O-12`][rf-o-12]
  > - [`RF-M-19`][rf-m-19] a [`RF-M-21`][rf-m-21]

**Flujo principal**

1. El operador consulta el diagnóstico de la corrida y sus diferencias con la vigente.
2. Inspecciona capas y celdas como las verá el público.
3. Publica la corrida.
4. El sistema genera las capas y descargas, las sube a la CDN y escribe el respaldo estático.
5. Marca la corrida como publicada y vigente de su región.

!!! example "**Alternativas**"

    === "**3a**"

        **El diagnóstico muestra un desfase de calibración anómalo**

        El operador excluye la adquisición ([`CU-O-06`](#cu-o-06)) y lanza otra
        corrida en lugar de publicar.

    === "**4a**"

        **Falla la subida a la CDN**

        La corrida no pasa a publicada y la vigente anterior sigue siéndolo; el
        operador reintenta.

- **Postcondición:** La API pública y el respaldo estático muestran la versión nueva.

### CU-O-11

> **Retirar una corrida**

- **Actor:** [Operador][act-operador]
- **Precondición:** La corrida está publicada
- **Requerimientos:**
  > - [`RF-O-13`][rf-o-13]

**Flujo principal**

1. El operador retira la corrida con un motivo.
2. Si era la vigente, el sistema vuelve vigente a la publicada anterior y actualiza el respaldo estático.
3. Las rutas de la versión retirada pasan a responder `410`.

!!! example "**Alternativas**"

    === "**2a**"

        **No hay otra corrida publicada en la región**

        El sistema rechaza el retiro: una región pública no queda sin vigente.
        El operador puede desactivar la región ([`RF-O-03`][rf-o-03]).

- **Postcondición:** La versión ya no se ofrece; sus resultados se purgan en treinta días.

### CU-O-12

> **Incorporar un reproceso de NASA**

- **Actor:** [Proceso programado][act-proceso] y [Operador][act-operador]
- **Precondición:** NASA publicó versiones nuevas de pasadas ya ingeridas
- **Requerimientos:**
  > - [`RF-M-05`][rf-m-05]
  > - [`RF-O-10`][rf-o-10]

**Flujo principal**

1. La sincronización encuentra productos de pasadas existentes con CRID más reciente.
2. El sistema crea las adquisiciones nuevas y marca las anteriores como reemplazadas.
3. El operador lanza una corrida con la madurez nueva, que sube la versión menor.
4. Revisa y publica la corrida, por [`CU-O-10`](#cu-o-10).

!!! example "**Alternativas**"

    === "**3a**"

        **El reproceso cubre solo parte de la serie**

        Una corrida con la madurez nueva tendrá menos fechas que la vigente. El
        operador decide si publicarla o esperar, por [`RN-01`][rn-01].

- **Postcondición:** La versión vigente usa los productos más recientes de una sola madurez.

### CU-O-13

> **Atender una alerta**

- **Actor:** [Operador][act-operador]
- **Precondición:** El sistema envió una alerta
- **Requerimientos:**
  > - [`RF-O-14`][rf-o-14]

**Flujo principal**

1. El operador abre el estado de procesos y credenciales.
2. Identifica la causa: token por vencer, disco lleno o sincronización fallida.
3. Renueva el token en el almacén de secretos, libera espacio o corrige la región.
4. Lanza una sincronización manual para confirmar.

- **Postcondición:** Los procesos programados vuelven a correr sin error.

### CU-O-14

> **Consultar la bitácora**

- **Actor:** [Operador][act-operador]
- **Precondición:** Sesión de operación
- **Requerimientos:**
  > - [`RF-O-15`][rf-o-15]

**Flujo principal**

1. El operador filtra la bitácora por entidad, cuenta o rango de fechas.
2. El sistema devuelve los eventos con el valor anterior y el nuevo.

- **Postcondición:** El operador sabe quién publicó, excluyó o retiró qué y cuándo.

[act-admin]: ../actores/operacion.md#administrador
[act-operador]: ../actores/operacion.md#operador
[act-proceso]: ../actores/index.md#proceso-programado
[rf-m-01]: ../requerimientos/funcionales/motor.md#rf-m-01
[rf-m-05]: ../requerimientos/funcionales/motor.md#rf-m-05
[rf-m-07]: ../requerimientos/funcionales/motor.md#rf-m-07
[rf-m-08]: ../requerimientos/funcionales/motor.md#rf-m-08
[rf-m-10]: ../requerimientos/funcionales/motor.md#rf-m-10
[rf-m-18]: ../requerimientos/funcionales/motor.md#rf-m-18
[rf-m-19]: ../requerimientos/funcionales/motor.md#rf-m-19
[rf-m-21]: ../requerimientos/funcionales/motor.md#rf-m-21
[rf-m-24]: ../requerimientos/funcionales/motor.md#rf-m-24
[rf-o-01]: ../requerimientos/funcionales/operacion.md#rf-o-01
[rf-o-02]: ../requerimientos/funcionales/operacion.md#rf-o-02
[rf-o-03]: ../requerimientos/funcionales/operacion.md#rf-o-03
[rf-o-04]: ../requerimientos/funcionales/operacion.md#rf-o-04
[rf-o-05]: ../requerimientos/funcionales/operacion.md#rf-o-05
[rf-o-06]: ../requerimientos/funcionales/operacion.md#rf-o-06
[rf-o-07]: ../requerimientos/funcionales/operacion.md#rf-o-07
[rf-o-08]: ../requerimientos/funcionales/operacion.md#rf-o-08
[rf-o-09]: ../requerimientos/funcionales/operacion.md#rf-o-09
[rf-o-10]: ../requerimientos/funcionales/operacion.md#rf-o-10
[rf-o-11]: ../requerimientos/funcionales/operacion.md#rf-o-11
[rf-o-12]: ../requerimientos/funcionales/operacion.md#rf-o-12
[rf-o-13]: ../requerimientos/funcionales/operacion.md#rf-o-13
[rf-o-14]: ../requerimientos/funcionales/operacion.md#rf-o-14
[rf-o-15]: ../requerimientos/funcionales/operacion.md#rf-o-15
[rn-01]: ../requerimientos/reglas-negocio.md#rn-01
[rn-10]: ../requerimientos/reglas-negocio.md#rn-10
[rnf-04]: ../requerimientos/no-funcionales.md#rnf-04
