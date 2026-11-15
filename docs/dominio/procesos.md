---
hide:
  - toc
icon: lucide/rotate-cw-fading-clock
---

# Procesos programados

Lo que el sistema hace sin que nadie lo pida. Cada proceso es una función de
servicio envuelta en un comando de gestión con un candado consultivo
(`pglock.advisory`) por región, para que dos ejecuciones solapadas no se pisen:
la segunda se salta. Los procesos periódicos los dispara un temporizador de
`systemd` en la instancia. Las corridas pendientes las toma un trabajador
directamente de la tabla `Corrida`: bloquea la más antigua con
`SELECT ... FOR UPDATE SKIP LOCKED`, la pasa a `en_proceso` y la calcula, de
modo que varios trabajadores nunca toman la misma.

Ningún proceso valida nada por su cuenta. Fija el actor `sistema`, escribe, y los
triggers de cada tabla imponen las reglas igual que si la escritura viniera de
la API.

|                Proceso                 |           Frecuencia           |                   Origen                    |         Comando          |
| :------------------------------------: | :----------------------------: | :-----------------------------------------: | :----------------------: |
|          Sincronizar regiones          |        Cada seis horas         | [`RF-M-01`][rf-m-01] a [`RF-M-07`][rf-m-07] | `sincronizar [--region]` |
|         Obtener lluvia diaria          |             Diaria             |            [`RF-M-08`][rf-m-08]             |     `obtenerlluvia`      |
|      Ejecutar corridas pendientes      |            Continua            | [`RF-M-10`][rf-m-10] a [`RF-M-18`][rf-m-18] | `trabajador --continuo`  |
| Proponer una corrida tras datos nuevos | Al terminar una sincronización |            [`RF-M-22`][rf-m-22]             | dentro de `sincronizar`  |
|       Purgar corridas retiradas        |             Diaria             |            [`RF-O-13`][rf-o-13]             |     `purgarcorridas`     |
|     Verificar credenciales y disco     |             Diaria             |            [`RF-O-14`][rf-o-14]             |     `verificarsalud`     |
|     Limpiar la lista de revocación     |             Diaria             |                  Template                   |     `cleanblocklist`     |

La sincronización termina, si recortó productos nuevos, creando una corrida
pendiente con el perfil predeterminado y la madurez más reciente disponible,
salvo que ya haya una pendiente en la región. El trabajador la calcula y queda
completada para revisión, no publicada.

## Comandos de operación

Lo que el operador ejecuta a mano desde la instancia. Cada comando llama al
mismo servicio que usaría la API de operación.

|         Comando         |                                                 Qué hace                                                 |        Origen        |
| :---------------------: | :------------------------------------------------------------------------------------------------------: | :------------------: |
|      `crearregion`      |                    Crea una región desde un archivo WKT o GeoJSON y congela su grilla                    | [`RF-O-02`][rf-o-02] |
|     `cargarinsumo`      |                              Carga una versión nueva de un insumo auxiliar                               | [`RF-O-04`][rf-o-04] |
|      `cargarserie`      |                                    Carga un CSV de marea o de lluvia                                     | [`RF-O-07`][rf-o-07] |
| `sincronizar --estimar` |                     Lista los productos que traería una sincronización, sin recortar                     | [`RF-O-08`][rf-o-08] |
|     `crearcorrida`      |                Crea una corrida pendiente con la madurez, el perfil y los tracks pedidos                 | [`RF-O-10`][rf-o-10] |
|    `ejecutarcorrida`    |                            Calcula una corrida pendiente en el mismo proceso                             | [`RF-O-10`][rf-o-10] |
|    `publicarcorrida`    | Genera las capas y descargas, las sube a la CDN, escribe el respaldo estático y marca la corrida vigente | [`RF-O-12`][rf-o-12] |
|    `retirarcorrida`     |                                Retira una corrida publicada con un motivo                                | [`RF-O-13`][rf-o-13] |

Publicar no es un trabajo en cola: ocurre dentro de la petición o del comando
que lo pide, en una transacción. Si falla la subida de un archivo, la corrida
sigue completada y la vigente anterior no cambia.

## Lo que no es un proceso programado

|                 Tentación                  |                                             Por qué no                                              |
| :----------------------------------------: | :-------------------------------------------------------------------------------------------------: |
| Publicar automáticamente la última corrida |          Publicar afirma algo sobre el manglar en nombre del equipo; lo decide una persona          |
|  Excluir adquisiciones con baja cobertura  | La cobertura baja puede ser legítima (borde de franja); el operador decide con [`RF-O-06`][rf-o-06] |
|   Reemplazar adquisiciones reprocesadas    |          No hay nada que barrer: lo hace la sincronización al registrar el producto nuevo           |
|   Retirar corridas viejas por antigüedad   |             Una versión vieja publicada sigue siendo citable; solo se retira con motivo             |
|       Renovar el token de Earthdata        |            El token se emite con la cuenta personal en Earthdata; el sistema solo avisa             |

[rf-m-01]: ../requerimientos/funcionales/motor.md#rf-m-01
[rf-m-07]: ../requerimientos/funcionales/motor.md#rf-m-07
[rf-m-08]: ../requerimientos/funcionales/motor.md#rf-m-08
[rf-m-10]: ../requerimientos/funcionales/motor.md#rf-m-10
[rf-m-18]: ../requerimientos/funcionales/motor.md#rf-m-18
[rf-m-19]: ../requerimientos/funcionales/motor.md#rf-m-19
[rf-m-21]: ../requerimientos/funcionales/motor.md#rf-m-21
[rf-m-22]: ../requerimientos/funcionales/motor.md#rf-m-22
[rf-o-02]: ../requerimientos/funcionales/operacion.md#rf-o-02
[rf-o-04]: ../requerimientos/funcionales/operacion.md#rf-o-04
[rf-o-06]: ../requerimientos/funcionales/operacion.md#rf-o-06
[rf-o-07]: ../requerimientos/funcionales/operacion.md#rf-o-07
[rf-o-08]: ../requerimientos/funcionales/operacion.md#rf-o-08
[rf-o-10]: ../requerimientos/funcionales/operacion.md#rf-o-10
[rf-o-12]: ../requerimientos/funcionales/operacion.md#rf-o-12
[rf-o-13]: ../requerimientos/funcionales/operacion.md#rf-o-13
[rf-o-14]: ../requerimientos/funcionales/operacion.md#rf-o-14
