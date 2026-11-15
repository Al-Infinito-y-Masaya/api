---
icon: lucide/gavel
---

# Reglas de negocio

Las reglas que ningún cálculo, comando ni petición puede romper. La mayoría son
reglas científicas: si se violan, el mapa sigue viéndose bien y está mal.

## RN-01

> **Una corrida, una sola madurez de datos**

Una corrida usa productos de una sola madurez (`provisional` o `validado`). La
guía de usuario de NISAR advierte que las diferencias entre madurezas pueden
deberse al cambio de procesamiento y no a cambios en el terreno. Mezclarlas
puede fabricar un punto de cambio CUSUM en la fecha en que cambió la madurez:
una pérdida de copa que no existe.

- **Mecanismo:** `Corrida.madurez` y trigger que rechaza agregar a `CorridaFecha` una adquisición de otra madurez
- **Origen:** [`RF-M-03`][rf-m-03], [`RF-O-10`][rf-o-10]

## RN-02

> **El reproceso reemplaza, no duplica**

Una misma pasada (track, frame, órbita, instante de inicio al minuto) puede
publicarse varias veces con distinto CRID. Gana la de CRID más reciente. La
versión anterior no se borra: queda marcada como reemplazada y la nueva apunta
a ella, para que las corridas viejas sigan siendo reproducibles.

- **Mecanismo:** `Adquisicion.reemplaza_a` e índice único parcial sobre la pasada (`pasada_at`) donde la adquisición no fue reemplazada
- **Origen:** [`RF-M-05`][rf-m-05]

## RN-03

> **La grilla de una región es inmutable**

Una región tiene una proyección UTM, un origen, un tamaño de celda y unas
dimensiones fijas desde que se crea. Cambiar cualquiera de ellos es crear otra
región. Las celdas, los resultados y los enlaces compartidos dependen de esa
grilla.

- **Mecanismo:** trigger de solo lectura sobre `epsg`, `celda_m`, `x0`, `y0`, `ancho` y `alto` de `Region`
- **Origen:** [`RF-O-02`][rf-o-02]

## RN-04

> **El identificador de una celda sale de sus coordenadas**

El identificador de una celda es `c_<E>_<N>`, con las coordenadas UTM de su
centro en metros. No es su posición en un arreglo. Así sobrevive a cambios de
tamaño del polígono y se puede calcular desde cualquier punto sin consultar la
base de datos.

- **Mecanismo:** `Celda.codigo` derivado por trigger a partir de la grilla de `Region`, la fila y la columna
- **Origen:** [`RF-C-07`][rf-c-07], [`RF-C-08`][rf-c-08]

## RN-05

> **Se promedia en potencia lineal**

La retrodispersión se promedia en escala lineal (γ⁰) y solo después se pasa a
decibeles. Promediar decibeles subestima el brillo de las celdas mixtas, que son
justamente las del borde del manglar.

- **Mecanismo:** función de agregación del motor, cubierta por pruebas con valores conocidos
- **Origen:** [`RF-M-06`][rf-m-06]

## RN-06

> **Las comparaciones en el tiempo se hacen dentro del mismo track**

La retrodispersión depende del ángulo de incidencia, y cada track ve la región
con un ángulo distinto. El promedio multitemporal, la calibración relativa, el
detector de cambios y el coeficiente de variación se calculan por track. CUSUM
recorre la serie de anomalías de cada celda respecto a la media de su propio
track. Los umbrales absolutos de clase se aplican a los valores calibrados.

- **Mecanismo:** `Adquisicion.track` y cálculo agrupado por track en el motor
- **Origen:** [`RF-M-10`][rf-m-10], [`RF-M-15`][rf-m-15], [`RF-M-16`][rf-m-16]

## RN-07

> **Cinco clases por fecha**

Cada celda recibe en cada fecha una de cinco clases: `IV` vegetación inundada,
`OW` agua abierta, `NI` no inundado, `NC` no clasificado y `ND` sin dato. `ND`
aparece cuando la celda no tuvo muestras válidas en esa pasada; nunca se rellena
con la fecha vecina.

- **Mecanismo:** `ResultadoCelda.clases` como arreglo de códigos con `CHECK` de valores admitidos
- **Origen:** [`RF-M-11`][rf-m-11]

## RN-08

> **Nivel de marea por adquisición**

Cada fecha se etiqueta `alta`, `media`, `baja` o `desconocida` según la altura
de marea en el instante de la pasada y los umbrales del perfil. `desconocida`
significa que no hay estimación de marea, y una fecha sin marea nunca cuenta
como marea alta.

- **Mecanismo:** `CorridaFecha.marea_nivel`, derivado al crear la fila y congelado
- **Origen:** [`RF-M-07`][rf-m-07]

## RN-09

> **La lluvia separa la marea del aguacero**

Una fecha con lluvia acumulada en los tres días previos igual o mayor al umbral
del perfil no cuenta para la frecuencia de inundación en marea alta. Así, el agua
de lluvia no se confunde con agua de marea.

- **Mecanismo:** `CorridaFecha.usada_en_if_alta`, calculada por el motor
- **Origen:** [`RF-M-08`][rf-m-08], [`RF-M-13`][rf-m-13]

## RN-10

> **Pocas fechas de marea alta no alcanzan para afirmar nada**

Si una celda tiene menos fechas de marea alta válidas que el mínimo del perfil,
su `if_alta` es nulo y queda marcada con datos insuficientes. No se la declara
conectada ni desconectada.

- **Mecanismo:** `CHECK` que exige `if_alta` nulo cuando `datos_suficientes` es falso
- **Origen:** [`RF-M-13`][rf-m-13]

## RN-11

> **Definición de manglar desconectado**

Una celda está desconectada si cumple todo lo siguiente: está dentro de la
máscara de manglar, tiene datos suficientes, su `if_alta` está bajo el umbral
del perfil y, si hay modelo de elevación y el perfil lo pide, su cota indica que
debería inundarse en marea alta. Después se aplica un voto de mayoría 3 × 3 para
quitar celdas sueltas por ruido.

- **Mecanismo:** `CHECK` de coherencia entre `desconectada`, `en_mascara` y `datos_suficientes`
- **Origen:** [`RF-M-14`][rf-m-14]

## RN-12

> **Fuera de la máscara no hay métricas**

Una celda fuera de la máscara de manglar conserva su serie de retrodispersión
y sus clases, pero no tiene `if`, `if_alta`, desconexión, probabilidad de error
ni punto de cambio.

- **Mecanismo:** `CHECK` que exige las métricas nulas cuando `en_mascara` es falso
- **Origen:** [`RF-O-04`][rf-o-04], [`RF-C-07`][rf-c-07]

## RN-13

> **Un cambio se reporta solo si es significativo**

Un punto de cambio en HV se publica solo si su confianza de bootstrap alcanza el
umbral del perfil y la caída de HV supera la mínima. Si no, el cambio es nulo.
Un cambio débil publicado como hallazgo es peor que no publicarlo.

- **Mecanismo:** `CHECK` que exige fecha, confianza y delta juntos o los tres nulos
- **Origen:** [`RF-M-15`][rf-m-15]

## RN-14

> **Una corrida publicada no cambia**

Los resultados de una corrida no se editan. Para corregir algo se crea otra
corrida. Una corrida publicada solo puede pasar a retirada, y una retirada no
vuelve a publicarse.

- **Mecanismo:** resultados de solo inserción y trigger de transiciones de `Corrida.estado`
- **Origen:** [`RF-O-12`][rf-o-12], [`RF-O-13`][rf-o-13]

## RN-15

> **Versión semántica de los datos**

Cada corrida tiene una versión `MAYOR.MENOR.PARCHE`, única por región. Sube el
mayor cuando cambia la forma del contrato, el menor cuando entran adquisiciones
o insumos nuevos, y el parche cuando solo cambian los umbrales. Los enlaces
compartidos incluyen la versión, así que siguen mostrando lo mismo aunque se
publique otra.

- **Mecanismo:** `unq_corrida_region_version` y `CHECK` de formato
- **Origen:** [`RF-C-03`][rf-c-03]

## RN-16

> **Los hallazgos son hipótesis**

Un manglar desconectado es un punto a verificar en campo, no una acusación. La
API no asocia estanques, bordas ni caminos con propietarios ni concesionarios, y
todo valor publicado viaja con su incertidumbre.

- **Mecanismo:** ausencia de datos de titularidad en el modelo; `p_error` y `confianza` obligatorios
- **Origen:** [`RF-C-07`][rf-c-07], [`RNF-12`][rnf-12]

## RN-17

> **Las brechas de datos se declaran**

Los períodos sin adquisiciones del instrumento, como el de NISAR entre el 27 de
julio y el 10 de agosto de 2026, se registran y se publican en el manifiesto.
Nunca se interpolan.

- **Mecanismo:** `Brecha` con rango temporal y restricción de exclusión contra solapamientos
- **Origen:** [`RF-C-02`][rf-c-02]

## RN-18

> **Instantes en UTC, fechas en hora local de la región**

Todo instante se guarda en UTC. Cuando hace falta una fecha de calendario, como
para sumar la lluvia de tres días, se resuelve en la zona horaria de la región.
Una pasada a las 00:16 UTC ocurre la tarde anterior en Nicaragua. El
identificador de fecha del contrato usa la fecha UTC.

- **Mecanismo:** `Region.zona_horaria` y columnas `timestamptz`
- **Origen:** [`RF-M-08`][rf-m-08], [`RF-C-02`][rf-c-02]

[rf-c-02]: funcionales/consulta.md#rf-c-02
[rf-c-07]: funcionales/consulta.md#rf-c-07
[rf-c-08]: funcionales/consulta.md#rf-c-08
[rf-c-03]: funcionales/consulta.md#rf-c-03
[rf-m-03]: funcionales/motor.md#rf-m-03
[rf-m-05]: funcionales/motor.md#rf-m-05
[rf-m-06]: funcionales/motor.md#rf-m-06
[rf-m-07]: funcionales/motor.md#rf-m-07
[rf-m-08]: funcionales/motor.md#rf-m-08
[rf-m-10]: funcionales/motor.md#rf-m-10
[rf-m-11]: funcionales/motor.md#rf-m-11
[rf-m-13]: funcionales/motor.md#rf-m-13
[rf-m-14]: funcionales/motor.md#rf-m-14
[rf-m-15]: funcionales/motor.md#rf-m-15
[rf-m-16]: funcionales/motor.md#rf-m-16
[rf-o-02]: funcionales/operacion.md#rf-o-02
[rf-o-04]: funcionales/operacion.md#rf-o-04
[rf-o-10]: funcionales/operacion.md#rf-o-10
[rf-o-12]: funcionales/operacion.md#rf-o-12
[rf-o-13]: funcionales/operacion.md#rf-o-13
[rnf-12]: no-funcionales.md#rnf-12
