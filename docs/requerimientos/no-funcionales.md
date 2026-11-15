---
icon: lucide/gauge
---

# Requerimientos no funcionales

Los objetivos de rendimiento piensan en conexiones móviles comunes en
Centroamérica, no en fibra óptica, y los de infraestructura en un equipo sin
presupuesto de operación.

- **Total:** 16

|         ID          |    Categoría     |                  Requerimiento                   |                     Medida de verificación                     |
| :-----------------: | :--------------: | :----------------------------------------------: | :------------------------------------------------------------: |
| [`RNF-01`](#rnf-01) |   Rendimiento    |       La primera vista carga rápido en 4G        |     Manifiesto ≤ 30 KB y primera capa ≤ 300 KB comprimidos     |
| [`RNF-02`](#rnf-02) |   Rendimiento    |    Inspeccionar una celda se siente inmediato    |             p95 ≤ 200 ms en el servidor, sin caché             |
| [`RNF-03`](#rnf-03) |      Caché       | La mayoría de las lecturas no llega al servidor  |  Rutas con versión inmutables; tasa de aciertos de CDN ≥ 90 %  |
| [`RNF-04`](#rnf-04) |      Escala      |        Unas pocas regiones, bien servidas        | 5 regiones, 1 M de celdas y 200 adquisiciones por región y año |
| [`RNF-05`](#rnf-05) | Infraestructura  |         El motor corre junto a los datos         |      Instancia en AWS `us-west-2`; lectura directa de S3       |
| [`RNF-06`](#rnf-06) |  Almacenamiento  |         El disco crece con lo necesario          |  Recortes nativos, no productos completos; ≤ 10 GB/región/año  |
| [`RNF-07`](#rnf-07) |   Arquitectura   |        API y motor en una sola instancia         |           `compose.yml` levanta todo en una máquina            |
| [`RNF-08`](#rnf-08) |  Disponibilidad  |    La app funciona aunque la API no responda     |       Con la API detenida, mapa, fechas y resumen cargan       |
| [`RNF-09`](#rnf-09) |    Seguridad     |   Las credenciales de Earthdata no se filtran    |     Nunca en el repositorio, en registros ni en respuestas     |
| [`RNF-10`](#rnf-10) |    Seguridad     |        La API pública no se puede saturar        |     Límite de tasa por IP; exploraciones con límite propio     |
| [`RNF-11`](#rnf-11) | Reproducibilidad |    Cualquier persona regenera los resultados     |          Misma entrada, mismos artefactos byte a byte          |
| [`RNF-12`](#rnf-12) |  Ética y datos   |    No se exponen datos personales ni se acusa    |         Sin cookies de rastreo ni datos de titularidad         |
| [`RNF-13`](#rnf-13) |     Apertura     |             Código y datos abiertos              |             Código MIT; datos derivados CC BY 4.0              |
| [`RNF-14`](#rnf-14) |  Accesibilidad   | Las capas se leen con cualquier visión del color |           Ninguna capa depende solo de rojo y verde            |
| [`RNF-15`](#rnf-15) |  Mantenibilidad  |        El motor es modular y está probado        |      Un módulo por etapa; pruebas con la escena sintética      |
| [`RNF-16`](#rnf-16) |  Observabilidad  |        Se sabe qué hizo el motor y cuándo        |   Cada ejecución registrada; alertas por correo al operador    |

---

## RNF-01

> **Primera vista en menos de tres segundos sobre 4G**

El manifiesto de una región con 31 fechas pesa menos de 30 KB comprimido y la
primera capa menos de 300 KB. La app nunca descarga la serie completa de una
región, que para 230 000 celdas y 31 fechas ronda los 30 MB: recibe capas ya
dibujadas y celdas una por una.

## RNF-02

> **Una celda en menos de 200 ms**

La serie de una celda es una sola fila leída por llave, con sus arreglos de HH,
HV y clases. El objetivo es el percentil 95 en el servidor, sin caché, sobre una
corrida de 230 000 celdas y 31 fechas.

## RNF-03

> **Caché por versión**

Las respuestas de rutas con versión llevan
`Cache-Control: public, max-age=31536000, immutable` y `ETag`. Las rutas sin
versión, como el manifiesto vigente, como máximo `max-age=300`. Las capas y
descargas se sirven desde Bunny CDN.

## RNF-04

> **Escala objetivo**

El diseño apunta a cinco regiones, cada una de hasta un millón de celdas de
1 ha, con hasta 200 adquisiciones por año, y a mantener las tres últimas
corridas publicadas por región. Más allá de eso hace falta revisar
[`D-04`][d-04] y [`D-06`][d-06].

## RNF-05

> **Instancia en `us-west-2`**

La instancia corre en AWS `us-west-2`, donde ASF guarda NISAR, porque la lectura
directa de S3 con credenciales de Earthdata solo funciona desde esa región y es
gratuita dentro de ella. Fuera de ella el motor sigue funcionando por HTTPS, más
lento. Referencia: una `t3.medium` con 50 GB `gp3`.

## RNF-06

> **Almacenamiento acotado**

En disco solo viven los recortes a resolución nativa (unos 50 a 100 MB por
adquisición y región) y las grillas agregadas. Los productos completos (unos 6 GB
cada uno) nunca se guardan. Antes de cada recorte el motor comprueba el espacio
libre y se detiene si no alcanza.

## RNF-07

> **Una sola instancia**

La API, PostgreSQL, Redis y el trabajador del motor corren en la misma instancia
con `compose.yml`. La app web se publica aparte como sitio estático (GitHub
Pages o Vercel).

## RNF-08

> **Respaldo estático**

Al publicar una corrida, el motor deja en la CDN el manifiesto, las capas, los
resúmenes y las descargas con la forma del contrato. Si la API no responde, la
app usa el respaldo y solo pierde el inspector de celdas y la exploración de
umbrales.

## RNF-09

> **Credenciales de Earthdata**

El token de Earthdata vive en AWS Systems Manager Parameter Store o en un archivo
de entorno legible solo por el servicio. No aparece en el repositorio, en los
registros, en la bitácora ni en ninguna respuesta. Las credenciales temporales
de S3 se renuevan cinco minutos antes de vencer.

## RNF-10

> **Protección de la API pública**

Las rutas públicas tienen límite de tasa por IP con el mecanismo del template.
Las exploraciones de umbrales, que sí calculan, tienen un límite más estricto y
un tiempo máximo de cálculo de cinco segundos.

## RNF-11

> **Reproducibilidad**

El código, los perfiles de umbrales y la lista de gránulos de cada corrida son
públicos. Con ellos y los insumos declarados, cualquier persona regenera la
corrida y obtiene los mismos artefactos byte a byte. El bootstrap usa semilla
fija.

## RNF-12

> **Ética y privacidad**

Sin cookies de rastreo y sin datos personales en la API pública. Los textos y
las leyendas presentan los hallazgos como hipótesis por verificar, por
[`RN-16`][rn-16].

## RNF-13

> **Apertura y atribución**

Código con licencia MIT y datos derivados con CC BY 4.0. El manifiesto y la ruta
de método llevan los créditos de NASA, ISRO, ASF, ESA (Copernicus DEM), Global
Mangrove Watch y demás fuentes, con su licencia.

## RNF-14

> **Accesibilidad de las capas**

Como el backend dibuja las capas, la accesibilidad del color es su
responsabilidad: paletas aptas para daltonismo, que no dependen solo de rojo y
verde, y leyendas con contraste de al menos 4,5:1. La API devuelve códigos, no
textos; los textos en español e inglés son del frontend.

## RNF-15

> **Mantenibilidad**

Un módulo por etapa del motor (ingesta, agregación, clasificación, métricas,
capas, publicación), cada uno con pruebas. Una escena sintética generada con un
modelo físico simple, que trae su propia verdad, es el dato de prueba de la
clasificación y de las métricas.

## RNF-16

> **Observabilidad**

Cada sincronización y cada corrida registran su inicio, su fin, su resultado y
sus conteos. El operador recibe un correo cuando una sincronización falla tres
veces seguidas, cuando el disco supera el 80 % y quince días antes de que venza
el token de Earthdata.

[d-04]: ../dominio/decisiones.md#d-04
[d-06]: ../dominio/decisiones.md#d-06
[rn-16]: reglas-negocio.md#rn-16
