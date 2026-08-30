Backend for the Tecnologías Web y Móviles semester project: the API of a
fictional vendor that
installs and operates dissolved-oxygen sensors in southern-Chile salmon
farms. One API, two frontends — a web monitoring dashboard that opens
interventions when it spots a problem, and a mobile field-technician app
that configures everything and closes them.

**All data is fictional.** Site names, codes and coordinates are invented;
nothing here describes a real installation.

**Auth**: `POST /token` with an OAuth2 form (`username`, `password`) returns a
JWT; send it as `Authorization: Bearer <token>`. A fresh boot only has the
fallback `admin` user; the seed script (`python -m scripts.seed`, run on
demand) adds `dashboard` and `tech`. Password equals username for all three.

**Sensor status is derived, not stored**: `no_data` (nothing received in 90
minutes), `out_of_range` (last value outside the operating range), or `ok`.

**Timezone contract**: every timestamp in requests and responses is Chile
local time (America/Santiago), ISO-8601 **without** a `Z` suffix. The database
stores UTC; the API converts at the boundary.

**Response conventions**: paginated lists return
`{"data": [...], "meta": {"totalCount": N, "page": p, "pageSize": s}}`;
detail and creation return the flat document; errors are `{"detail": ...}`
with 400, 401, 404, 409 or 422 — `detail` is a string, except on 422 where
FastAPI returns a list of objects, one per failing field.
