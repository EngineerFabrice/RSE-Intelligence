import datetime
import decimal

from flask import jsonify
from sqlalchemy import inspect


def _serialize_value(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def to_dict(instance, exclude=()):
    if instance is None:
        return None
    mapper = inspect(instance).mapper
    return {
        col.key: _serialize_value(getattr(instance, col.key))
        for col in mapper.columns
        if col.key not in exclude
    }


def ok(data=None, **extra):
    payload = {"status": "success"}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def error(message, code="error", http_status=400):
    return jsonify(status="error", code=code, message=message), http_status


def paginated(query, page, per_page, serializer):
    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [serializer(i) for i in items],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page if per_page else 0,
    }
