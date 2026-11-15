<div align="center">
  <img
    src="docs/logo.svg"
    width="100"
    height="100"
    style="padding: 10px;"
  />
</div>

<h1 align="center">
  <code>mangroove-api</code>
</h1>

<p align="center">
  API y motor de análisis de Mangroove.
</p>

<div align="center">

[![PostgreSQL.][postgres-badge]][postgres-docs]
[![Django.][django-badge]][django-docs]
[![OpenAPI.][openapi-badge]][openapi-docs]
<br/>
[![ruff.][ruff-badge]][ruff-docs]
[![ty.][ty-badge]][ty-docs]
[![uv.][uv-badge]][uv-docs]

</div>

---

Mangroove se divide en una aplicación web interactiva y este backend.

El backend tiene tres partes:

1. El motor de análisis que lee los productos NISAR L2 (GCOV y GUNW) directo desde
  S3 en `us-west-2`, recorta la ventana de cada región y calcula los resultados
  por celda de una hectárea, cruzando cada fecha con la altura de la marea.
1. La API de consulta, pública y de solo lectura. Entrega a la aplicación web
  las capas como PNG georreferenciados, las leyendas y los resultados por celda.
  Además, se publica un respaldo estático en la CDN para que la app funcione
  aunque la API no responda.
1. La API de operación, protegida y usada solo por el equipo de Mangroove para
  registrar regiones, cargar insumos como mareas, lluvia y estanques, lanzar
  corridas de análisis y publicar la vigente.

Cada corrida es inmutable y guarda las adquisiciones, los insumos y los umbrales
exactos que usó, porque NASA publica productos provisionales y reprocesa las
fechas viejas. Las garantías críticas, como no mezclar madurezas de producto o
no publicar una desconexión sin su confianza, viven en PostgreSQL como
restricciones y triggers.

Para más detalle, visitar [la documentación](https://docs.mangroove.earth).

[django-badge]: https://img.shields.io/badge/django-white?style=for-the-badge&color=757a5d&logoColor=e3e8c4&logo=django
[django-docs]: https://docs.djangoproject.com/en/
[docs-actores]: docs/actores/index.md
[docs-casos-uso]: docs/casos-uso/consulta.md
[docs-dominio]: docs/dominio/alcance.md
[docs-requerimientos]: docs/requerimientos/index.md
[openapi-badge]: https://img.shields.io/badge/openapi-white?style=for-the-badge&color=757a5d&logoColor=e3e8c4&logo=openapiinitiative
[openapi-docs]: https://www.openapis.org/
[postgres-badge]: https://img.shields.io/badge/postgresql-white?style=for-the-badge&color=757a5d&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzOTQuNSA0MDgiPjxwYXRoIGZpbGw9IiNlM2U4YzQiIGQ9Ik0zODMuMiAyNTIuNWMtNTAuMyAxMC40LTUzLjgtNi42LTUzLjgtNi42QzM4Mi42IDE2NyA0MDQuOCA2NyAzODUuNiA0Mi42IDMzMy4zLTI0LjIgMjQyLjggNy40IDI0MS4zIDguMmgtLjVxLTE0LjgtMy0zMy41LTMuNGMtMjIuOC0uNC00MCA2LTUzLjEgMTUuOSAwIDAtMTYxLjUtNjYuNS0xNTQgODMuNkMyIDEzNi4zIDQ2IDM0NiA5OC44IDI4Mi42YzE5LjMtMjMuMiAzNy45LTQyLjcgMzcuOS00Mi43YTQ5IDQ5IDAgMCAwIDMxLjkgOC4xbC45LS44Yy0uMyAzLS4xIDUuNy40IDktMTMuNiAxNS4yLTkuNiAxNy45LTM2LjggMjMuNS0yNy40IDUuNi0xMS4zIDE1LjctLjggMTguMyAxMi44IDMuMiA0Mi40IDcuOCA2Mi4zLTIwLjJsLS44IDMuMmM1LjMgNC4zIDkgMjcuNyA4LjQgNDktLjYgMjEuMi0xIDM1LjggMy4yIDQ3LjJzOC40IDM3IDQ0IDI5LjRjMjkuOC02LjQgNDUuMy0yMyA0Ny40LTUwLjUgMS42LTE5LjYgNS0xNi43IDUuMi0zNC4zbDIuOC04LjNjMy4yLTI2LjYuNS0zNS4yIDE4LjktMzEuMmw0LjQuNGMxMy42LjYgMzEuMi0yLjIgNDEuNi03IDIyLjQtMTAuNCAzNS42LTI3LjcgMTMuNi0yMy4yIi8+PC9zdmc+Cg==
[postgres-docs]: https://www.postgresql.org/docs/
[ruff-badge]: https://img.shields.io/badge/ruff-white?style=for-the-badge&color=757a5d&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0MCA0MCI+PHBhdGggZmlsbD0iI2UzZThjNCIgZmlsbC1ydWxlPSJldmVub2RkIiBkPSJNNDAgNGE0IDQgMCAwIDAtNC00SDB2NDBoMTguNFYyOGgzLjJ2MTJINDBWMjQuOGgtOHYtMy4yaDRhNCA0IDAgMCAwIDQtNFpNMjQuOCAxNS4ydjMuMmgtOS42di0zLjJ6IiBjbGlwLXJ1bGU9ImV2ZW5vZGQiLz48L3N2Zz4K
[ruff-docs]: https://docs.astral.sh/ruff
[ty-badge]: https://img.shields.io/badge/ty-white?style=for-the-badge&color=757a5d&logoColor=e3e8c4&logo=ty
[ty-docs]: https://docs.astral.sh/ty
[uv-badge]: https://img.shields.io/badge/uv-white?style=for-the-badge&color=757a5d&logoColor=e3e8c4&logo=uv
[uv-docs]: https://docs.astral.sh/uv
