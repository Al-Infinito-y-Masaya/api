---
icon: lucide/cpu
---

# Motor de análisis

Lo que el backend hace con los datos de NISAR sin que nadie lo mire: buscarlos,
recortarlos, agregarlos, clasificarlos, medirlos y publicarlos. Corre dentro de
procesos programados y comandos de gestión, nunca dentro de una petición HTTP.

- **Módulos:** 5
- **Total:** 24

La prioridad sigue MoSCoW: _debe_ es imprescindible para la primera versión,
_debería_ es importante pero no bloquea la entrega y _podría_ se hace si sobra
tiempo.

---

## Ingesta

### RF-M-01

> **Descubrir productos GCOV por región**

Para cada región activa, el motor busca en ASF con `asf_search` los productos
NISAR L2 GCOV que intersectan su polígono más el margen de recorte, en ambas
direcciones de órbita y en todas las madurezas disponibles. Cada producto
encontrado se registra una sola vez, identificado por su nombre de gránulo. La
búsqueda no requiere credenciales y se repite cada seis horas.

- **Prioridad:** Debe
- **Criterio de aceptación:** una segunda búsqueda sin productos nuevos no crea filas

### RF-M-02

> **Recortar cada producto a la región desde S3**

El motor lee de S3, con credenciales temporales de Earthdata, solo los chunks
HDF5 que cubren la región más su margen: HH, HV, la máscara de validez, las
coordenadas, la proyección y el ángulo de incidencia. Guarda el recorte a
resolución nativa en disco, en un HDF5 comprimido con la misma estructura
interna que el producto original, con su suma SHA-256. El producto completo
nunca se descarga. Fuera de `us-west-2` el motor cae a lectura por HTTPS con
peticiones de rango.

- **Prioridad:** Debe
- **Criterio de aceptación:** el recorte pesa menos del 2 % del producto y reproduce los valores del original en la ventana

### RF-M-03

> **Registrar los metadatos del producto**

De cada producto se guardan track, frame, ciclo, dirección de órbita, instante
de inicio y fin, CRID, madurez, fecha de procesamiento, polarizaciones, URL de
S3, URL HTTPS y tamaño. La madurez se deduce de la colección de origen
(`NISAR_L2_GCOV_PROVISIONAL_V1`, `NISAR_L2_GCOV_V1`, etc.), no del nombre del
archivo.

- **Prioridad:** Debe
- **Criterio de aceptación:** todo producto recortado tiene madurez y CRID no vacíos

### RF-M-04

> **Consolidar productos en adquisiciones**

Una adquisición es una pasada del satélite sobre una región. Si la región cae en
dos frames de la misma pasada (mismo track y dirección, inicio a menos de dos
minutos), sus recortes se combinan en una sola adquisición. La adquisición
guarda la cobertura: la fracción de celdas de la región con muestras válidas.

- **Prioridad:** Debe
- **Criterio de aceptación:** dos frames contiguos de la misma pasada producen una adquisición

### RF-M-05

> **Aplicar reprocesos**

Cuando llega un producto de una pasada que ya tiene adquisición vigente, pero con
CRID más reciente, el motor crea la adquisición nueva y marca la anterior como
reemplazada, por [`RN-02`][rn-02]. Si el CRID es igual o más viejo, el producto
se registra y se descarta con motivo.

- **Prioridad:** Debe
- **Criterio de aceptación:** nunca hay dos adquisiciones vigentes de la misma pasada

---

## Preparación

### RF-M-06

> **Agregar a la grilla de la región**

Cada adquisición se agrega a la grilla de la región: promedio en potencia lineal
de HH y HV de todas las muestras válidas que caen en cada celda, por
[`RN-05`][rn-05]. Por defecto solo cuentan las muestras totalmente enfocadas
(máscara 1 a 254). El resultado se guarda en disco como arreglo de la grilla,
para que una corrida nueva no repita la agregación.

- **Prioridad:** Debe
- **Criterio de aceptación:** la agregación de un recorte sintético con valores conocidos da el promedio esperado

### RF-M-07

> **Estimar la marea de cada adquisición**

El motor calcula con `pyTMD` la altura de marea en el instante de la pasada, en
el punto de referencia de la región, con el modelo configurado (por defecto
TPXO9-atlas). Admite también alturas cargadas a mano por el operador. Si hay
varias estimaciones, la corrida usa la del modelo que declara.

- **Prioridad:** Debe
- **Criterio de aceptación:** toda adquisición vigente tiene marea estimada o queda con nivel `desconocida`

### RF-M-08

> **Obtener la lluvia diaria**

El motor obtiene la precipitación diaria de la región desde GPM IMERG (NASA) con
`earthaccess`, promediada sobre el polígono, y la suma en los tres días locales
previos a cada pasada, por [`RN-18`][rn-18]. El operador puede cargar en su
lugar una serie de una estación.

- **Prioridad:** Debería
- **Criterio de aceptación:** cada fecha de una corrida tiene su lluvia de tres días o nulo explícito

### RF-M-09

> **Agregar la coherencia de GUNW**

Si hay productos GUNW de pares que terminan en una adquisición, el motor agrega
su coherencia a la grilla y la asigna a la fecha secundaria del par. La
coherencia alta sobre una celda que parece agua abierta indica lodazal.

- **Prioridad:** Podría
- **Criterio de aceptación:** menos celdas `OW` sobre lodazales, verificado con imagen óptica

### RF-M-10

> **Calibración relativa por track**

Para cada track, el motor calcula el promedio multitemporal de cada celda y el
desfase de cada fecha respecto a ese promedio, como la mediana sobre celdas
estables (fuera de humedal). Ese desfase se resta a la fecha, por
[`RN-06`][rn-06]. El desfase de cada fecha queda guardado en la corrida.

- **Prioridad:** Debe
- **Criterio de aceptación:** las celdas estables no varían más que el umbral configurado entre fechas del mismo track

---

## Clasificación y métricas

### RF-M-11

> **Clasificar cada fecha**

Cada celda recibe en cada fecha una de las clases de [`RN-07`][rn-07] según el
método de la sección 6.4 del manual de NISAR, con los umbrales del perfil de la
corrida. La clase típica de la celda sale de su promedio multitemporal.

- **Prioridad:** Debe
- **Criterio de aceptación:** la clasificación de la escena sintética de prueba coincide con su verdad en al menos el 90 % de las celdas

### RF-M-12

> **Estimar la probabilidad de error**

Cada celda en máscara tiene una probabilidad de error entre 0 y 1: el promedio,
sobre sus fechas, de la probabilidad de que el ruido de speckle (σ del perfil)
la haya cruzado al otro lado del umbral más cercano.

- **Prioridad:** Debe
- **Criterio de aceptación:** las celdas más lejos de todos los umbrales tienen menor `p_error`

### RF-M-13

> **Calcular IF e IF_alta**

`if` es la fracción de fechas con clase `IV` u `OW`. `if_alta` es lo mismo solo
sobre las fechas de marea alta que no fueron excluidas por lluvia. Junto a cada
valor se guarda cuántas fechas lo respaldan, y se aplica [`RN-10`][rn-10].

- **Prioridad:** Debe
- **Criterio de aceptación:** los valores están entre 0 y 1 y cada uno trae su número de fechas

### RF-M-14

> **Marcar el manglar desconectado**

El motor aplica [`RN-11`][rn-11] y guarda una marca booleana por celda. Si hay
modelo de elevación, guarda también la inundación esperada por cota: la fracción
de fechas de marea alta en que la marea supera la cota de la celda.

- **Prioridad:** Debe
- **Criterio de aceptación:** en la escena sintética, la precisión y la exhaustividad de la desconexión son de al menos 0,8

### RF-M-15

> **Detectar el inicio del deterioro**

Sobre cada celda en máscara, el motor aplica CUSUM a la serie de anomalías de
HV y estima su significancia con bootstrap (120 permutaciones por defecto, con
semilla fija). Publica la primera fecha después del cambio, la confianza y la
diferencia de HV medio, por [`RN-13`][rn-13].

- **Prioridad:** Debería
- **Criterio de aceptación:** dos corridas con los mismos datos y perfil dan los mismos cambios

### RF-M-16

> **Clasificar estanques activos y abandonados**

Para cada estanque digitalizado, el motor calcula el coeficiente de variación de
HH y HV dentro de cada track y lo promedia. Sobre el umbral es activo, porque se
llena y se vacía; bajo el umbral es abandonado. Los abandonados se ordenan como
candidatos a restauración por distancia al canal abierto, área y frecuencia de
inundación del manglar vecino.

- **Prioridad:** Podría
- **Criterio de aceptación:** cada estanque tiene su CV, su clase y, si es abandonado, su puntaje

### RF-M-17

> **Probar las hipótesis de trabajo**

El motor evalúa las hipótesis del proyecto con la prueba de Mann-Whitney:
H1, si el manglar junto a bordas se inunda menos en marea alta que el manglar
junto a canales a la misma cota; H2, si pierde más copa; H3, si los estanques
abandonados están más cerca de manglar desconectado. Guarda el estadístico, el
valor p, el tamaño del efecto y los tamaños de muestra.

- **Prioridad:** Debería
- **Criterio de aceptación:** una prueba con menos de cinco celdas por grupo se guarda como no evaluable, no como no significativa

### RF-M-18

> **Resumir por país y por fecha**

El motor calcula las hectáreas de manglar, de manglar desconectado, con datos
insuficientes y con pérdida de copa por país, y las hectáreas de cada clase por
país y fecha.

- **Prioridad:** Debe
- **Criterio de aceptación:** la suma por países coincide con el total de la región

---

## Publicación

### RF-M-19

> **Generar las capas del mapa**

Por cada fecha de la corrida, el motor genera un compuesto RGB (R = HH, G = HV,
B = HH − HV en dB) y un mapa de clases. Para la corrida completa genera
`if_alta`, `if`, desconexión, probabilidad de error y cambio. Cada capa es un
PNG reproyectado a Web Mercator, con sus esquinas en lon/lat, con paletas aptas
para daltonismo y transparencia fuera de la región.

- **Prioridad:** Debe
- **Criterio de aceptación:** ninguna capa depende solo de rojo y verde; cada PNG pesa menos de 300 KB

### RF-M-20

> **Generar las descargas**

Las mismas capas se exportan como GeoTIFF optimizados para la nube en la
proyección de la región, con valores numéricos en vez de colores, junto con el
resumen en CSV y un archivo de metadatos.

- **Prioridad:** Debería
- **Criterio de aceptación:** los GeoTIFF abren en QGIS alineados con la grilla de la región

### RF-M-21

> **Publicar en la CDN y dejar el respaldo estático**

Al publicar una corrida, el motor sube sus capas y descargas a Bunny Storage y
escribe además el manifiesto y los resúmenes con la forma del
[contrato][contrato], para que la app pueda funcionar sin la API.

- **Prioridad:** Debe
- **Criterio de aceptación:** con la API detenida, la app muestra mapas, línea de tiempo y resumen

---

## Operación del motor

### RF-M-22

> **Procesar solo lo nuevo**

Una sincronización solo recorta y agrega las adquisiciones que no tienen
recorte. Las corridas sí recalculan todas las métricas: con la grilla ya
agregada, clasificar y medir una región toma segundos.

- **Prioridad:** Debe
- **Criterio de aceptación:** una sincronización sin productos nuevos no transfiere datos de S3

### RF-M-23

> **Resultados reproducibles**

Una corrida registra la versión del código, la versión del perfil de umbrales,
los CRID de sus adquisiciones y la suma de cada insumo. Repetirla con lo mismo
da exactamente los mismos resultados.

- **Prioridad:** Debe
- **Criterio de aceptación:** dos ejecuciones de la misma corrida producen artefactos con la misma suma SHA-256

### RF-M-24

> **Registrar cada ejecución y aislar las fallas**

Cada sincronización queda registrada con su región, inicio, fin, productos
encontrados, recortados, descartados y fallidos. Un producto que falla no detiene
el lote: queda marcado como fallido con su error y se reintenta en la siguiente
sincronización, hasta tres veces.

- **Prioridad:** Debe
- **Criterio de aceptación:** un corte de red a mitad de un lote deja los demás productos recortados

[contrato]: ../../dominio/contrato.md
[rn-02]: ../reglas-negocio.md#rn-02
[rn-05]: ../reglas-negocio.md#rn-05
[rn-06]: ../reglas-negocio.md#rn-06
[rn-07]: ../reglas-negocio.md#rn-07
[rn-10]: ../reglas-negocio.md#rn-10
[rn-11]: ../reglas-negocio.md#rn-11
[rn-13]: ../reglas-negocio.md#rn-13
[rn-18]: ../reglas-negocio.md#rn-18
