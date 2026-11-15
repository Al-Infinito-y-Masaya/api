---
icon: lucide/folder-lock
---

# Operación

Lo que el equipo de Mangroove hace desde la API protegida: declarar regiones,
cargar insumos, revisar lo que el motor trajo, correr análisis y decidir qué se
publica. No hay una interfaz gráfica de operación en la primera versión: se
opera con la API documentada en OpenAPI y con comandos de gestión.

- **Módulos:** 5
- **Total:** 15

---

## Acceso

### RF-O-01

> **Acceso de operación**

Las rutas de operación exigen sesión de una cuenta con rol de personal o de
administrador, con el mecanismo de autenticación del template: JWT, correo
verificado y segundo factor obligatorio. No hay registro público de cuentas de
operación; las crea un administrador.

- **Prioridad:** Debe
- **Criterio de aceptación:** una petición anónima o de una cuenta sin rol recibe `401` o `403`

---

## Regiones e insumos

### RF-O-02

> **Registrar una región**

El operador declara una región con su código, su nombre, su polígono en WKT o
GeoJSON (lon/lat), su zona horaria, su punto de referencia de marea y,
opcionalmente, su tamaño de celda (100 m por defecto) y su margen de recorte
(2 km por defecto). El sistema elige la zona UTM del centroide, calcula la
grilla y crea sus celdas. A partir de ahí la grilla no cambia, por
[`RN-03`][rn-03].

- **Prioridad:** Debe
- **Criterio de aceptación:** la región creada informa su EPSG, su origen, su ancho, su alto y su número de celdas

### RF-O-03

> **Desactivar una región**

Una región desactivada deja de sincronizarse y de aparecer en el listado
público, pero sus corridas publicadas siguen respondiendo en sus enlaces con
versión.

- **Prioridad:** Debería
- **Criterio de aceptación:** los enlaces con versión de una región desactivada siguen respondiendo `200`

### RF-O-04

> **Cargar un insumo auxiliar**

El operador sube un insumo de la región: máscara de manglar (GMW), modelo de
elevación (Copernicus GLO-30), zonas de exclusión, bordas y caminos, estanques,
límites de países o áreas protegidas, en GeoTIFF o GeoJSON, con su fuente y su
licencia. Cada carga es una versión nueva del insumo de ese tipo; las corridas
anteriores conservan la versión que usaron. El sistema rasteriza el insumo a la
grilla de la región al cargarlo y rechaza archivos que no la cubren.

- **Prioridad:** Debe
- **Criterio de aceptación:** cargar una máscara nueva no altera los resultados de una corrida ya publicada

---

## Adquisiciones y datos auxiliares

### RF-O-05

> **Consultar productos y adquisiciones**

Listado de productos por región con su estado (descubierto, recortado,
descartado, fallido), y de adquisiciones con fecha, track, órbita, madurez,
CRID, cobertura, incidencia, marea y, si aplica, la adquisición que la
reemplazó. Filtros por estado, madurez, track, órbita y rango de fechas.

- **Prioridad:** Debe
- **Criterio de aceptación:** el filtro por madurez separa las fechas `provisional` de las `validado`

### RF-O-06

> **Excluir o restituir una adquisición**

El operador excluye una adquisición de las corridas futuras con un motivo
obligatorio (franja incompleta, interferencia, geolocalización dudosa). La
exclusión no borra nada y se revierte con otro motivo.

- **Prioridad:** Debe
- **Criterio de aceptación:** una corrida nueva no incluye la adquisición excluida y la anterior sí la conserva

### RF-O-07

> **Cargar marea o lluvia manual**

El operador carga una serie CSV de marea (`datetime,tide_m`, UTC) o de lluvia
diaria (`date,rain_mm`, fecha local) para una región, con su fuente. La marea se
interpola al instante de cada adquisición y queda como otro modelo de marea.

- **Prioridad:** Debería
- **Criterio de aceptación:** una corrida puede elegir entre el modelo global y la serie cargada

### RF-O-08

> **Lanzar una sincronización**

El operador puede adelantar la sincronización programada de una región, con un
rango de fechas opcional. Si ya hay una sincronización en curso para esa región,
la petición se rechaza en lugar de lanzar otra.

- **Prioridad:** Debe
- **Criterio de aceptación:** dos peticiones seguidas lanzan una sola sincronización

---

## Análisis

### RF-O-09

> **Gestionar perfiles de umbrales**

Un perfil es un conjunto con nombre de todos los umbrales del método: agua
abierta, vegetación inundada, cambio, fuera de modelo, coherencia, marea alta y
baja, lluvia, desconexión, mínimo de fechas, speckle, CUSUM, estanques, mayoría y
uso de la elevación. Editar un perfil crea una versión nueva; las corridas
apuntan a una versión, nunca a la última. Hay tres perfiles iniciales:
`estricto`, `predeterminado` y `permisivo`.

- **Prioridad:** Debe
- **Criterio de aceptación:** cambiar el perfil predeterminado no altera los umbrales que muestra una corrida anterior

### RF-O-10

> **Lanzar una corrida**

El operador crea una corrida de una región indicando madurez, versión del perfil,
modelo de marea, tracks u órbitas incluidas y, opcionalmente, un rango de fechas.
El sistema propone la versión semántica según [`RN-15`][rn-15], fija la lista de
adquisiciones y los insumos vigentes y la encola. El cálculo corre fuera de la
petición.

- **Prioridad:** Debe
- **Criterio de aceptación:** la petición responde `202` con la corrida en estado pendiente

### RF-O-11

> **Revisar una corrida**

Antes de publicar, el operador consulta el diagnóstico de la corrida: desfase de
calibración por fecha, cobertura por fecha, número de fechas de marea alta,
hectáreas por clase y diferencias con la corrida vigente. Puede ver las mismas
capas y celdas que verá el público.

- **Prioridad:** Debe
- **Criterio de aceptación:** una corrida no publicada se puede inspeccionar completa sin hacerla pública

### RF-O-12

> **Publicar una corrida**

Publicar una corrida completada la vuelve la vigente de su región para el
público, sube sus artefactos a la CDN y escribe el respaldo estático. La
vigente anterior sigue disponible en su versión.

- **Prioridad:** Debe
- **Criterio de aceptación:** tras publicar, `/regiones/{codigo}/manifest` redirige a la versión nueva

### RF-O-13

> **Retirar una corrida**

Retirar una corrida publicada la quita del listado de versiones, con un motivo
obligatorio. Si era la vigente, vuelve a serlo la publicada anterior. Sus
resultados se conservan treinta días y luego se purgan; sus enlaces responden
`410`.

- **Prioridad:** Debería
- **Criterio de aceptación:** retirar la vigente nunca deja a una región con corridas publicadas sin vigente

### RF-O-14

> **Estado de los procesos y las credenciales**

El operador consulta el estado de las últimas sincronizaciones y corridas, el
espacio libre en disco y el vencimiento del token de Earthdata. El sistema
avisa por correo a las cuentas de operación quince días antes de que venza el
token y cuando una sincronización falla tres veces seguidas.

- **Prioridad:** Debería
- **Criterio de aceptación:** un token vencido aparece como tal antes de que falle una sincronización

---

## Auditoría

### RF-O-15

> **Bitácora de operación**

Toda escritura de operación queda registrada con la cuenta, el instante, la
entidad y el valor anterior, con `pghistory`. La bitácora es de solo lectura.

- **Prioridad:** Debe
- **Criterio de aceptación:** publicar y retirar una corrida deja dos eventos con la cuenta que actuó

[rn-03]: ../reglas-negocio.md#rn-03
[rn-15]: ../reglas-negocio.md#rn-15
