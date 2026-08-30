# ulamonitors

Backend for the FDICI11 "Tecnologías Móviles y Web" semester project: the API
of a fictional vendor that installs and operates dissolved-oxygen sensors in
southern-Chile salmon farms. One API, two frontends with clearly split roles:

- The **web** app is the admin's monitoring dashboard: registered sites, what
  each sensor is delivering, and what is wrong — values out of range and
  transmission outages. Its only write is opening an intervention to flag a
  problem for the technician.
- The **mobile** app is the field technician tool: it registers and
  configures sites and sensors, and closes interventions saying what
  happened in the field.

Measurements are produced by the sensors themselves — simulated by a
scheduler job — so what the technician changes in the field visibly changes
what the dashboard shows.

**All data is fictional.** Every site name, code, coordinate and user in the
seed is invented. Site codes start with `9` so they cannot collide with any
real industry code, and coordinates are randomized inside a southern-Chile
bounding box pointing at no existing installation. Nothing in this repository
describes a real company, client or site.

## Quickstart

```bash
docker compose up --build
```

That starts MongoDB and the API on <http://localhost:8000>. A fresh boot
starts with an **empty** database: the only thing the API creates on startup
is the fallback `admin`/`admin` user. To load the demo data, run the seed
script once:

```bash
docker compose exec api python -m scripts.seed
```

That populates 8 sites, 32 sensors, 3 users, ~16 interventions and ~43,600
measurements covering the last 30 days. Re-running it on a seeded database
does nothing; `--reset` drops the collections and repopulates. Interactive
docs live at <http://localhost:8000/docs>.

The history is not uniform: it tells four stories, so charts differ between
sensors. On `/measurements/overview` each one is visible at a glance:

- **Ongoing outage** — the line ends before the right edge and never
  resumes. Sensor 7 stopped ~3 days ago, sensor 13 ~6 days ago, sensor 22
  ~12 hours ago. All three derive `no_data`.
- **Gap and recovery** — a hole in the middle of the series, then the line
  resumes: what a repaired sensor looks like. Sensor 4 has a 2-day hole
  ending ~10 days ago, sensor 18 a 12-hour hole ~5.5 days ago.
- **Late install** — `installed_at` falls inside the window, so the line
  starts mid-chart. Sensor 10 was installed ~12 days ago, sensor 27 ~8 days
  ago.
- **Healthy** — a full continuous 30-day series, e.g. sensor 1. Hypoxia
  excursions still dip below range periodically on every sensor, so an
  `out_of_range` sensor shows the excursion across its whole series, not
  only in the last value.

## Seed users

Password equals username — deliberate, this is a classroom API.

| user | scopes | represents |
|---|---|---|
| `admin` | all | maintenance |
| `dashboard` | `profile`, `read` | the web app — reads, and opens interventions |
| `tech` | `profile`, `read`, `field` | the mobile app — the field writer |

The role split between the two apps is visible in the scopes: `dashboard`
gets 401 on every POST and PATCH except `POST /interventions`, which only
needs `read` — reporting what you observe is for anyone logged in.

## Authentication

`POST /token` takes an OAuth2 **form** (not JSON) and returns a JWT. From the
browser or React Native:

```js
const res = await fetch("http://localhost:8000/token", {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ username: "dashboard", password: "dashboard" }),
});
const { access_token } = await res.json();

// Then, on every request:
const sites = await fetch("http://localhost:8000/sites", {
  headers: { Authorization: `Bearer ${access_token}` },
});
```

Requesting no scopes gives you all the scopes your user has. Requesting a
scope your user does not have returns 401. Tokens last 8 hours in the compose
setup, a full class session.

## Sensor status

A sensor's `status` is derived on every read, never stored:

- `no_data` — no reading received in the last 90 minutes. Sensors transmit
  over satellite internet; a storm cuts the signal and the data stops until
  the antenna reconnects. The dashboard must show the absence of data, not
  only bad data.
- `out_of_range` — the last value falls outside the sensor's
  `[oxygen_min, oxygen_max]` operating range.
- `ok` — anything else.

`GET /sensors?status=no_data` and `?status=out_of_range` are the dashboard's
outage and alert panels; `meta.totalCount` with `page_size=1` is the KPI.

## Timezone contract

Every timestamp the API accepts or returns is **Chile local time**
(America/Santiago, DST-aware), ISO-8601 **without** a `Z` suffix, e.g.
`2026-08-20T13:00:00`. The database stores UTC and the API converts at the
boundary in both directions, so daily chart buckets align to Chilean
midnight, not UTC midnight.

## Response conventions

- Paginated lists: `{"data": [...], "meta": {"totalCount": N, "page": p, "pageSize": s}}`.
- Detail and creation: the flat document.
- Errors: `{"detail": ...}` with 400 (invalid request), 401 (credentials or
  insufficient scope), 403 (one case, below), 404 (not found), 409
  (conflict), 422 (validation).
- On 400, 401, 403, 404 and 409, `detail` is a string. On 422 — FastAPI's own
  validation error — `detail` is a **list of objects**, one per failing
  field, not a string.
- The 400s you can hit: `GET /measurements` with neither `sensor_id` nor
  `site_id`, an unknown `medition` on `GET /measurements` or
  `GET /measurements/overview`, non-numeric `depths` on the overview,
  `oxygen_min >= oxygen_max` on `PATCH /sensors/{id}`, and authenticating as
  a disabled user.

## Endpoints

| Method and path | Scope | Notes |
|---|---|---|
| `GET /` | public | healthcheck |
| `POST /token` | public | OAuth2 form → JWT |
| `GET /users/me` | `profile` | own profile |
| `POST /users` | `admin` | create user |
| `GET /users` | `admin` | list users |
| `GET /sites` | `read` | `?q&area&active&page&page_size` |
| `GET /sites/{id}` | `read` | detail + sensors with derived status |
| `POST /sites` | `field` | 201 |
| `PATCH /sites/{id}` | `field` | partial update |
| `GET /sensors` | `read` | `?site_id&status&position&page&page_size` |
| `GET /sensors/{id}` | `read` | detail with derived status |
| `POST /sensors` | `field` | 201, register a sensor on a site |
| `PATCH /sensors/{id}` | `field` | configure depth, position, range, transmitting |
| `GET /measurements` | `read` | `?sensor_id\|site_id&from&to&page&page_size` |
| `GET /measurements/overview` | `read` | `?site_id&bucket&days&depths`, chart data |
| `GET /interventions` | `read` | `?site_id&sensor_id&status&page&page_size` |
| `POST /interventions` | `read` | 201, opens; `opened_by` comes from the token |
| `PATCH /interventions/{id}` | `field` | closes with an `outcome`; 409 if already closed |

An intervention has an open/close lifecycle: `POST` with
`{site_id, sensor_id?, reason}` opens it (`sensor_id` null means the whole
site), `PATCH` with `{outcome, outcome_notes?}` closes it — `outcome` is one
of `back_online`, `replaced`, `reconfigured` or `no_fault_found`. `opened_by`,
`closed_by` and `closed_at` are set by the server from the token, never from
the body. A `POST` that already brings an `outcome` is born closed: the
technician acting on their own initiative — that shortcut requires the
`field` scope and is the API's only 403. Registering a new sensor is
`POST /sensors`, not an intervention outcome.

There is no `POST /measurements`: sensors deliver on their own, technicians
do not type readings. There are no `DELETE`s either — an installed sensor is
not erased, it is switched off (`transmitting: false`) or replaced through an
intervention, and a site is deactivated with `PATCH {"active": false}`.

## Live data

The API ships a scheduler (enabled in compose) that inserts one simulated
reading per transmitting sensor every 5 minutes, so charts and last readings
keep moving during class. Sensors with `transmitting: false` receive nothing
and surface as `no_data` until a technician repairs them through the mobile
app. Hypoxia excursions follow a deterministic schedule, so at any moment a
couple of sensors are out of range.

## Reset

```bash
docker compose exec api python -m scripts.seed --reset
```

Drops the collections and repopulates. `docker compose down -v` also works —
it drops the whole volume, but the next boot comes up empty and you have to
run the seed script again. The seed is deterministic (`random.Random(42)`),
so every group gets the same data.

## Hosted deployment

The course runs one shared instance, so students point their frontend at a URL
and never bring the API up themselves. Built from the Dockerfile, with MongoDB
as a separate service. Compose stays as the local fallback.

```
MONGO_URI=mongodb://<user>:<pass>@<host>:27017/ulamonitors?authSource=admin
SECRET_KEY=<openssl rand -hex 32>
ENABLE_SCHEDULER=true
ACCESS_TOKEN_DURATION_MINUTES=480
CORS_ORIGINS=*
ENV=prod
```

**The database name must be in the URI path.** Managed MongoDB services hand
out a URI ending in `/` or `/?authSource=admin`, and `client.get_database()`
raises `ConfigurationError: No default database defined` on those. Append
`/ulamonitors` before the query string.

Load the demo data once from the running container:

```bash
python -m scripts.seed
```

### Nightly reset

A shared database is writable by every group. The `field` scope can flip
`transmitting` on a sensor, and the scheduler then feeds it again, so one
student ends a seeded outage story for the whole class. A scheduled task
restores everything at midnight Chile time:

```bash
python -m scripts.seed --reset
```

It runs against the live API without a restart. If the task scheduler is on
UTC, midnight in Chile is `0 3 * * *` from September to April and `0 4 * * *`
the rest of the year. Either one lands in the middle of the night.

This also caps disk. The collection never holds more than the seed plus one
day of simulated readings, roughly 52,000 documents and 4 MB, instead of
growing by 0.7 MB every day for the whole semester.

The reset drops `users` as well, so a per-group user created through
`POST /users` disappears with it. Add those to `USERS` in `scripts/seed.py`
if you want them to survive.

## Common pitfalls

- **CORS**: the API allows every origin without credentials; keep the JWT in
  the `Authorization` header, never in cookies.
- **401 vs 422 on `/token`**: 401 means wrong credentials or scopes; 422
  usually means you sent JSON — the token endpoint takes form encoding
  (`URLSearchParams`, `application/x-www-form-urlencoded`).
- **Timestamps**: no `Z` suffix anywhere. If your chart looks shifted by 3-4
  hours, you appended `Z` and re-converted Chile local time as UTC.

## License

MIT.
