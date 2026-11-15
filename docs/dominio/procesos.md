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
`systemd` en la instancia; los trabajos encolados (corridas y publicaciones) los
toma un trabajador que lee la cola de Redis.

Ningún proceso valida nada por su cuenta. Fija el actor `sistema`, escribe, y los
triggers de cada tabla imponen las reglas igual que si la escritura viniera de
la API.

|                Proceso                 |           Frecuencia           |                   Origen                    |         Comando          |
| :------------------------------------: | :----------------------------: | :-----------------------------------------: | :----------------------: |
|          Sincronizar regiones          |        Cada seis horas         | [`RF-M-01`][rf-m-01] a [`RF-M-07`][rf-m-07] | `sincronizar [--region]` |
|         Obtener lluvia diaria          |             Diaria             |            [`RF-M-08`][rf-m-08]             |     `obtenerlluvia`      |
|           Ejecutar corridas            |        Continua (cola)         | [`RF-M-10`][rf-m-10] a [`RF-M-18`][rf-m-18] |       `trabajador`       |
|           Publicar corridas            |        Continua (cola)         | [`RF-M-19`][rf-m-19] a [`RF-M-21`][rf-m-21] |       `trabajador`       |
| Proponer una corrida tras datos nuevos | Al terminar una sincronización |            [`RF-M-22`][rf-m-22]             | dentro de `sincronizar`  |
|       Purgar corridas retiradas        |             Diaria             |            [`RF-O-13`][rf-o-13]             |     `purgarcorridas`     |
|     Verificar credenciales y disco     |             Diaria             |            [`RF-O-14`][rf-o-14]             |     `verificarsalud`     |
|     Limpiar la lista de revocación     |             Diaria             |                  Template                   |     `cleanblocklist`     |

La sincronización termina, si trajo adquisiciones nuevas, encolando una corrida
con el perfil predeterminado y la madurez más reciente disponible. Esa corrida
queda completada para revisión, no publicada.

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
[rf-o-06]: ../requerimientos/funcionales/operacion.md#rf-o-06
[rf-o-13]: ../requerimientos/funcionales/operacion.md#rf-o-13
[rf-o-14]: ../requerimientos/funcionales/operacion.md#rf-o-14
