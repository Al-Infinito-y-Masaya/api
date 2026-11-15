---
icon: lucide/chart-network
---

# Decisiones transversales

## D-01

> **El backend procesa; el frontend presenta**

El prototipo empaquetaba la serie completa de la región en un JSON de 38,6 MB y
el navegador clasificaba, medía y corría el bootstrap de CUSUM sobre 230 000
celdas. En un teléfono sobre 4G eso no carga en tres segundos, y dos personas con
los controles en posiciones distintas veían dos mapas distintos sin saberlo.

Esta versión calcula todo en el backend y guarda el resultado como corrida. La
app recibe capas ya dibujadas, un manifiesto liviano y celdas una por una. La
exploración de umbrales se conserva, pero se calcula en el servidor y la
respuesta dice que es una exploración ([`D-07`](#d-07)).

El costo es operar un servidor, que el documento preliminar quería evitar. Se
acota con una sola instancia ([`RNF-07`][rnf-07]) y con un respaldo estático en
la CDN que mantiene la app en pie si la API cae ([`RNF-08`][rnf-08]).

## D-02

> **Instancia en `us-west-2` con recortes nativos, no productos completos**

Un producto GCOV pesa unos 6 GB y cada región recibe unos 7 por mes. Guardarlos
completos son unos 45 GB al mes por región. Desde `us-west-2`, donde ASF los
guarda en S3, leer solo la ventana de la región es rápido y gratuito, así que lo
que se guarda en disco es esa ventana a resolución nativa más un margen: de 50 a
100 MB por adquisición.

El recorte nativo, y no solo la grilla agregada a 1 ha, es lo que permite
cambiar el tamaño de celda o crear una región solapada sin volver a S3. Si un
recorte se pierde, se vuelve a leer: el gránulo de origen está en `Producto`.

## D-03

> **Grilla UTM por región, inmutable, con identificadores por coordenadas**

Cada región tiene su grilla en la zona UTM de su centroide, para que las celdas
sean cuadrados de 1 ha reales y no trapecios de grados. El identificador de una
celda es `c_<E>_<N>`, con las coordenadas de su centro en metros, por
[`RN-04`][rn-04].

El contrato preliminar usaba `c_\d{6}`, la posición en el arreglo. Con ese
esquema, agrandar el polígono renumera todas las celdas y rompe cada enlace
compartido. Con coordenadas, la app y la API calculan la celda de un clic con
aritmética, sin consultar nada. Cambiar la grilla es crear otra región, por
[`RN-03`][rn-03].

## D-04

> **La serie de una celda es una fila con arreglos, no una fila por fecha**

Una corrida de 230 000 celdas y 31 fechas son 7,1 millones de pares celda-fecha.
Como filas, inspeccionar una celda lee 31 filas dispersas y cada corrida inserta
millones. Como arreglos `smallint[]` alineados con `CorridaFecha.orden`, la celda
es una sola fila de unos 300 bytes leída por llave, y una corrida inserta 230 000
filas con `django-pgbulk`.

Los decibeles se guardan multiplicados por 100 en `smallint`, como en el
prototipo: dos bytes por valor, con precisión de 0,01 dB, que sobra frente a un
ruido de speckle de 0,9 dB. El sacrificio es que la base no puede filtrar por el
valor de una fecha dentro del arreglo sin desanidarlo. Ninguna consulta de la
API lo necesita: los filtros espaciales y temporales se resuelven en el motor.

## D-05

> **Corridas inmutables; publicar es marcar la vigente**

Una corrida no se edita, se reemplaza ([`RN-14`][rn-14]). Publicar es poner
`vigente = true` en una corrida completada; un índice único parcial garantiza una
sola vigente por región. Las rutas con versión no dependen de esa marca, por eso
un enlace viejo sigue respondiendo después de publicar otra versión.

Retirar una corrida no la borra en el acto: la marca, la quita del listado y
programa la purga de sus resultados a los treinta días. Es la única vía por la
que se borran filas de resultados.

## D-06

> **Capas como PNG por región, no como teselas**

La región más grande prevista, de 100 × 100 km, es una imagen de 1 000 × 1 000
celdas. Un PNG con paleta de esa imagen pesa menos de 300 KB y MapLibre lo
muestra con una fuente de imagen y sus cuatro esquinas. Las teselas vectoriales
o PMTiles que proponía el contrato preliminar suman una cadena de herramientas
(`tippecanoe`, `rio-pmtiles`) y una pirámide de niveles de zoom para un dato que
cabe en un archivo.

Si una región llega a superar unos 4 000 × 4 000 celdas, esta decisión se revisa.

## D-07

> **Las exploraciones viven en Redis, no en la base**

Recalcular clases y desconexión con otros umbrales sobre una corrida existente
toma menos de un segundo en numpy. Persistirlo como corrida inundaría la base de
resultados que nadie publicó. La respuesta se guarda en Redis veinticuatro horas
bajo la huella SHA-256 de la versión y los umbrales, y se marca como exploración.

## D-08

> **Sin PostGIS**

Las únicas operaciones espaciales que la API necesita son ubicar una celda a
partir de una coordenada y devolver un polígono. Lo primero es aritmética sobre
la grilla tras proyectar con `pyproj`; lo segundo es un `jsonb` con GeoJSON. Todo
el trabajo geométrico pesado (rasterizar, reproyectar, recortar) ocurre en el
motor con `rasterio` y `pyproj`. Instalar PostGIS agregaría una extensión al
servidor y a la imagen sin consultas que la aprovechen.

Si aparece un requerimiento de consulta espacial libre (por ejemplo, celdas
dentro de un polígono dibujado por el usuario), esta decisión se revisa.

## D-09

> **Archivos pesados en disco, con su suma en la base**

Los recortes HDF5, las grillas agregadas (`.npy`) y los insumos rasterizados
viven en el volumen de datos de la instancia. La base guarda la ruta relativa y
la suma SHA-256 de cada uno. Las rutas son relativas a `MANGROOVE_DATOS`, para
que mover el volumen no exija tocar filas.

Los archivos que el público descarga no están ahí: están en Bunny, registrados
como `ApiMedia` del template.

## D-10

> **Los insumos son versiones inmutables**

Cargar una máscara, un DEM o unos estanques nuevos crea una versión; nunca se
sobrescribe la anterior. La corrida registra qué versión usó cada tipo de insumo
en `CorridaInsumo`, y los resultados copian lo que de ellos depende (máscara,
humedal, país) en `ResultadoCelda`. Así, una corrida vieja se lee igual aunque
el insumo haya cambiado. Por eso `Celda` no tiene país ni máscara: son
propiedades de la corrida, no de la geometría.

## D-11

> **El producto es global; el recorte es por región**

Un producto de NISAR puede cubrir dos regiones vecinas. `Producto` guarda el
gránulo una sola vez y `Recorte` guarda, por región, el estado de la lectura, el
archivo y sus intentos. El estado de trabajo (pendiente, fallido, descartado)
vive en el recorte, porque leer la ventana de una región puede fallar sin que
falle la de la otra.

## D-12

> **La marea es una estimación por modelo**

Una adquisición puede tener varias alturas de marea: la del modelo global, la
interpolada de una estación, la de otro modelo para comparar. `EstimacionMarea`
guarda una por modelo, y la corrida elige cuál usar. El nivel (`alta`, `media`,
`baja`, `desconocida`) no se guarda en la estimación sino en `CorridaFecha`,
porque depende de los umbrales del perfil de esa corrida.

## D-13

> **Las reglas viven en la base**

Igual que en el template, las invariantes del dominio son `CHECK`, índices únicos
parciales y triggers de `django-pgtrigger`, no validaciones de servicio. El motor
escribe por comandos de gestión, el operador por la API y una migración de datos
por SQL; una regla en un servicio se saltaría en dos de los tres caminos.

## D-14

> **El cálculo es determinista**

El bootstrap de CUSUM usa una semilla guardada en la corrida y permutaciones
precalculadas iguales para todas las celdas, como en el prototipo. Los PNG y
GeoTIFF se escriben sin marcas de tiempo internas. Dos ejecuciones de la misma
corrida producen artefactos con la misma suma, por [`RF-M-23`][rf-m-23].

## D-15

> **El contrato v2 conserva los nombres del v1**

El contrato de datos que ya tiene el frontend (`manifest.json`, `Celda`, `Clase`,
`serieConMarea`) se conserva en nombres y en forma donde fue posible. Los cambios
son los que exigen las reglas de esta versión y están listados en el
[contrato][contrato].

[contrato]: contrato.md
[rf-m-23]: ../requerimientos/funcionales/motor.md#rf-m-23
[rn-03]: ../requerimientos/reglas-negocio.md#rn-03
[rn-04]: ../requerimientos/reglas-negocio.md#rn-04
[rn-14]: ../requerimientos/reglas-negocio.md#rn-14
[rnf-07]: ../requerimientos/no-funcionales.md#rnf-07
[rnf-08]: ../requerimientos/no-funcionales.md#rnf-08
