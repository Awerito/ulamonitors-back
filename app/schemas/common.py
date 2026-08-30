from app.utils.timezone import utc_to_chile


def paginated(data: list, *, total: int, page: int, page_size: int) -> dict:
    """Wrap a page of results in the data/meta envelope the frontends consume."""
    return {
        "data": data,
        "meta": {"totalCount": total, "page": page, "pageSize": page_size},
    }


def localize(doc: dict, fields: tuple[str, ...]) -> dict:
    """Convert the given stored-UTC datetime fields to naive Chile local."""
    for field in fields:
        if doc.get(field) is not None:
            doc[field] = utc_to_chile(doc[field])
    return doc
