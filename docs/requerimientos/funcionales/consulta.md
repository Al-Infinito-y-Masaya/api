---
icon: lucide/map
---

# Consulta pública

Lo que la aplicación web, o cualquier persona con un navegador, lee de la API
sin cuenta. Toda respuesta pública describe una corrida publicada: no hay
lectura de datos en proceso. La forma de cada respuesta está fijada en el
[contrato de datos][contrato].

- **Módulos:** 5
- **Total:** 15

---

## Entrada

### RF-C-01

> **Listar las regiones**

Listado de las regiones activas con su código, su nombre, su polígono, su
centro, su zoom inicial, la versión vigente y el instante de su última
publicación.

- **Prioridad:** Debe
- **Criterio de aceptación:** una región sin corridas publicadas no aparece

### RF-C-02

> **Obtener el manifiesto de una versión**

El manifiesto es lo primero que carga la app al abrir una región: grilla, polígono,
fechas con su marea, órbita, track, madurez y CRID, brechas de datos, capas
disponibles, perfil de umbrales completo y leyendas de cada capa. Existe una ruta
sin versión, que redirige a la versión vigente, y una ruta con versión, que es la
que se guarda en caché.

- **Prioridad:** Debe
- **Criterio de aceptación:** el manifiesto de una región con 31 fechas pesa menos de 30 KB comprimido

### RF-C-03

> **Enlaces permanentes**

Toda ruta pública de datos incluye la región y la versión. Un enlace compartido
con la capa, la fecha y el zoom muestra lo mismo aunque después se publique otra
versión, mientras esa versión no se retire.

- **Prioridad:** Podría
- **Criterio de aceptación:** un enlace de la versión anterior sigue mostrando sus datos tras publicar una nueva

---

## Mapas

### RF-C-04

> **Capas por fecha**

Para cada fecha de una versión, la API entrega el compuesto RGB y el mapa de
clases como PNG con sus esquinas georreferenciadas. La ruta redirige a la CDN.
Con esto la app arma la línea de tiempo, la animación y el deslizador entre dos
fechas.

- **Prioridad:** Debe
- **Criterio de aceptación:** cambiar de fecha después del primer recorrido responde desde caché

### RF-C-05

> **Capas de conectividad**

Para cada versión, la API entrega las capas de `if_alta`, `if`, manglar
desconectado, probabilidad de error y cambio de copa. La capa de desconexión
distingue con trama las celdas con datos insuficientes.

- **Prioridad:** Debe
- **Criterio de aceptación:** las celdas con datos insuficientes no se ven igual que las conectadas ni que las desconectadas

### RF-C-06

> **Comparador de sensores**

Para una fecha, la API entrega capas auxiliares de fechas cercanas de un sensor
óptico (Sentinel-2 o Landsat) y uno de banda C (Sentinel-1), con su fecha y su
porcentaje de nubes, para compararlas con NISAR sobre el mismo manglar.

- **Prioridad:** Podría
- **Criterio de aceptación:** cada capa auxiliar trae su fecha y su diferencia en días con la fecha de NISAR

---

## Celdas

### RF-C-07

> **Inspeccionar una celda por su identificador**

Devuelve la celda con su centroide, su país, si está en la máscara, sus métricas
(`if`, `if_alta`, número de fechas, desconexión, datos suficientes,
probabilidad de error, inundación esperada), su cambio de copa y su serie: por
cada fecha, HH, HV, coherencia y clase. La marea no se repite en la celda: viaja
en el manifiesto.

- **Prioridad:** Debe
- **Criterio de aceptación:** la respuesta llega en menos de 200 ms en el servidor

### RF-C-08

> **Inspeccionar una celda por coordenada**

Con una longitud y una latitud, la API calcula la celda que contiene el punto y
la devuelve igual que [`RF-C-07`][rf-c-07]. Un punto fuera de la grilla responde
`404` con el motivo.

- **Prioridad:** Debe
- **Criterio de aceptación:** un clic en el borde entre dos celdas devuelve siempre la misma

---

## Resultados

### RF-C-09

> **Resumen por país y por fecha**

Hectáreas de manglar, de manglar desconectado, con datos insuficientes y con
pérdida de copa, por país y para la región completa. Por fecha, hectáreas de
cada clase. En JSON o en CSV según el encabezado `Accept`.

- **Prioridad:** Debería
- **Criterio de aceptación:** las cifras coinciden con el CSV de descarga

### RF-C-10

> **Estanques y candidatos a restauración**

Listado de estanques de la versión con su área, su CV, su clase (activo o
abandonado), su distancia al canal, la frecuencia de inundación del manglar
vecino y, si es abandonado, su puntaje de restauración. Filtros por clase y
país; orden por puntaje, área, distancia o inundación vecina. Cada estanque trae
su polígono para resaltarlo en el mapa.

- **Prioridad:** Podría
- **Criterio de aceptación:** el orden por puntaje coincide con el ranking del motor

### RF-C-11

> **Pruebas de hipótesis**

Resultado de las pruebas H1 a H3 de la versión: grupos comparados, tamaños de
muestra, medianas, estadístico, valor p y tamaño del efecto, o el motivo por el
que no fue evaluable.

- **Prioridad:** Debería
- **Criterio de aceptación:** una prueba no evaluable lo dice explícitamente

### RF-C-12

> **Explorar con otros umbrales**

Con el nombre de otro perfil, o con umbrales propios dentro de rangos
permitidos, la API recalcula sobre la misma versión las clases, la desconexión y
el resumen, y devuelve la capa de conectividad y el resumen resultantes. El
resultado no se guarda como corrida: es una exploración y la respuesta lo dice.

- **Prioridad:** Debería
- **Criterio de aceptación:** pedir dos veces los mismos umbrales responde la segunda vez desde caché

---

## Método y datos

### RF-C-13

> **Método y fuentes**

Por versión: productos NISAR usados con su gránulo, CRID y madurez; insumos con
su fuente, versión, licencia y suma; perfil de umbrales; modelo de marea; versión
del código; supuestos y limitaciones; y créditos de NASA, ISRO, ASF y demás
fuentes.

- **Prioridad:** Debe
- **Criterio de aceptación:** cada insumo enlaza a su origen

### RF-C-14

> **Descargas**

Listado de archivos descargables de la versión: capas en GeoTIFF, resumen en CSV,
estanques en GeoJSON y metadatos en JSON, cada uno con su tamaño, su suma y su
licencia (CC BY 4.0). Las descargas se sirven desde la CDN.

- **Prioridad:** Debería
- **Criterio de aceptación:** cada archivo descargado coincide con la suma publicada

### RF-C-15

> **Respuestas que se guardan en caché**

Toda respuesta de una ruta con versión se marca como inmutable y lleva `ETag`.
Las rutas sin versión se guardan en caché como máximo cinco minutos.

- **Prioridad:** Debe
- **Criterio de aceptación:** una petición condicional repetida recibe `304`

[contrato]: ../../dominio/contrato.md
[rf-c-07]: #rf-c-07
