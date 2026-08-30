# ulamonitors

API de un proveedor ficticio de sensores de oxígeno disuelto para centros de
cultivo. Backend del proyecto de semestre del ramo Tecnologías Web y
Móviles.

Dos frontends sobre esta API: la **web** es el panel del administrador y solo
lee, salvo abrir intervenciones. El **móvil** es el técnico en terreno, que
registra y configura sensores y cierra intervenciones.

Todos los datos son ficticios.

## Levantar una instancia

```bash
cp sample.env .env      # define SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
docker compose up --build
docker compose exec api python -m scripts.seed
```

API en <http://localhost:8000>, docs interactivas en `/docs`.

El seed carga 8 centros, 32 sensores y 30 días de mediciones. Con `--reset`
borra y vuelve a sembrar. No toca los usuarios.

Los usuarios se crean con `POST /users`:

```bash
curl -X POST http://localhost:8000/users -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"username":"tech","password":"tech","scopes":["profile","read","field"]}'
```

| usuario | scopes | para |
|---|---|---|
| `dashboard` | `profile`, `read` | la web |
| `tech` | `profile`, `read`, `field` | el móvil |

## Autenticación

`POST /token` recibe un **form**, no JSON, y devuelve un JWT.

```js
const res = await fetch("http://localhost:8000/token", {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ username: "dashboard", password: "dashboard" }),
});
const { access_token } = await res.json();

const sites = await fetch("http://localhost:8000/sites", {
  headers: { Authorization: `Bearer ${access_token}` },
});
```

Sin pedir scopes recibes todos los que tenga tu usuario. Pedir uno que no
tiene da 401. El token dura 8 horas.

## Endpoints

| Método y ruta | Scope | Query params |
|---|---|---|
| `GET /` | público | healthcheck |
| `POST /token` | público | form, devuelve JWT |
| `GET /users/me` | `profile` | |
| `POST /users` | `admin` | |
| `GET /users` | `admin` | |
| `GET /sites` | `read` | `q`, `area`, `active`, `page`, `page_size` |
| `GET /sites/{id}` | `read` | centro + sus sensores |
| `POST /sites` | `field` | |
| `PATCH /sites/{id}` | `field` | |
| `GET /sensors` | `read` | `site_id`, `status`, `position`, `page`, `page_size` |
| `GET /sensors/{id}` | `read` | |
| `POST /sensors` | `field` | |
| `PATCH /sensors/{id}` | `field` | `depth`, `position`, rango, `transmitting` |
| `GET /measurements` | `read` | `sensor_id` o `site_id`, `from`, `to`, `page`, `page_size` |
| `GET /measurements/overview` | `read` | `site_id`, `bucket`, `days`, `depths` |
| `GET /interventions` | `read` | `site_id`, `sensor_id`, `status`, `page`, `page_size` |
| `POST /interventions` | `read` | abre |
| `PATCH /interventions/{id}` | `field` | cierra |

`POST /interventions` con `{site_id, sensor_id?, reason}` abre.
`PATCH` con `{outcome, outcome_notes?}` cierra, donde `outcome` es
`back_online`, `replaced`, `reconfigured` o `no_fault_found`. El servidor pone
`opened_by`, `closed_by` y `closed_at` desde el token.

No hay `POST /measurements` ni `DELETE` en ninguna parte. Un sensor se apaga
con `transmitting: false` y un centro con `active: false`.

## Respuestas

Listas paginadas:

```json
{"data": [...], "meta": {"totalCount": 32, "page": 1, "pageSize": 10}}
```

Detalle y creación devuelven el documento plano. Los errores vienen como
`{"detail": ...}`, con 401 credenciales o scope, 404 no existe, 409 conflicto,
422 validación. En 422 el `detail` es una lista de objetos, no un string.

## Estado del sensor

Se calcula al leer, nunca se guarda.

| status | significa |
|---|---|
| `no_data` | sin lecturas hace 90 minutos |
| `out_of_range` | último valor fuera de `[oxygen_min, oxygen_max]` |
| `ok` | el resto |

`GET /sensors?status=no_data` y `?status=out_of_range` son los paneles de
corte y de alerta.

## Timezone

Todas las fechas que entran y salen son hora de Chile, ISO-8601 **sin** `Z`:
`2026-08-20T13:00:00`. La base guarda UTC y el API convierte en el borde.

## Errores comunes

- **422 en `/token`**: mandaste JSON. Ese endpoint recibe form.
- **Gráfico corrido 3 o 4 horas**: le agregaste `Z` a una fecha que ya venía
  en hora de Chile.
- **CORS**: el JWT va en el header `Authorization`, no en cookies.

## Licencia

MIT.
