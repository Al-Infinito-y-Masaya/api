---
icon: lucide/user-round-pen
---

# Actores del sistema

Quién interactúa con cada superficie y qué puede hacer. Un actor es un papel, no
una persona: la misma persona puede leer el mapa como visitante y correr una
corrida como operador, con dos sesiones distintas.

- **Superficies:** 2
- **Actores humanos:** 3
- **Actores no humanos:** 5

---

## Matriz de capacidades

|               Capacidad               | Visitante | Operador | Administrador |
| :-----------------------------------: | :-------: | :------: | :-----------: |
| Ver regiones, mapas y línea de tiempo |    sí     |    sí    |      sí       |
|        Inspeccionar una celda         |    sí     |    sí    |      sí       |
|      Explorar con otros umbrales      |    sí     |    sí    |      sí       |
|      Descargar capas y resúmenes      |    sí     |    sí    |      sí       |
|      Ver corridas no publicadas       |    no     |    sí    |      sí       |
|    Registrar o desactivar regiones    |    no     |    sí    |      sí       |
|            Cargar insumos             |    no     |    sí    |      sí       |
|   Excluir o restituir adquisiciones   |    no     |    sí    |      sí       |
|    Gestionar perfiles de umbrales     |    no     |    sí    |      sí       |
|  Lanzar sincronizaciones y corridas   |    no     |    sí    |      sí       |
|      Publicar o retirar corridas      |    no     |    sí    |      sí       |
|         Consultar la bitácora         |    no     |    sí    |      sí       |
|      Crear cuentas de operación       |    no     |    no    |      sí       |

---

## Actores no humanos

### Proceso programado

> **El motor de análisis, corriendo sin intervención**

Busca productos nuevos, recorta, agrega, estima mareas, consolida reprocesos,
ejecuta las corridas encoladas, publica en la CDN, purga corridas retiradas y
avisa de credenciales por vencer. Sus escrituras quedan en la bitácora con actor
de tipo sistema, sin persona asociada. Ver [procesos programados][procesos].

### ASF y Earthdata

> **El archivo de NASA de donde salen los datos de radar**

ASF responde las búsquedas de productos y entrega, con el login de Earthdata,
credenciales temporales de S3 y lecturas por rango. No inicia interacciones. Su
indisponibilidad detiene la llegada de fechas nuevas, pero no afecta a lo ya
publicado: es la dependencia externa de mayor impacto, y por eso el motor
reintenta y la API nunca depende de ella para responder.

### Modelo de mareas

> **Constituyentes de marea locales, consultados con `pyTMD`**

Los archivos del modelo (TPXO o FES) viven en el disco de la instancia. No es un
servicio remoto, pero es un actor porque sus resultados entran a toda corrida y
su versión debe quedar registrada.

### GPM IMERG

> **Precipitación diaria de NASA, obtenida con `earthaccess`**

Fuente de la lluvia de tres días que separa la inundación por marea de la
inundación por aguacero. Su ausencia no detiene una corrida: deja la lluvia en
nulo y la corrida lo declara.

### CDN

> **Bunny Storage y su zona de distribución**

Recibe las capas, las descargas y el respaldo estático de cada corrida
publicada, y los sirve a la app. Si la API cae, sigue sirviendo el respaldo.

---

## Superficies

1. [Consulta pública](consulta.md)
1. [Operación](operacion.md)

[procesos]: ../dominio/procesos.md
