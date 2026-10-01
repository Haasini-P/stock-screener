"""
StockMind AI — Database Type Compatibility
Provides cross-database column types that work with both SQLite and PostgreSQL.
"""

import uuid
from sqlalchemy import Text, TypeDecorator
from sqlalchemy.types import CHAR


class CompatUUID(TypeDecorator):
    """
    Platform-independent UUID type.
    Uses PostgreSQL's UUID type when available, otherwise stores as CHAR(36).
    """
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(uuid.UUID(value))
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
        return value

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))


class CompatJSON(TypeDecorator):
    """
    Platform-independent JSON type.
    Uses PostgreSQL's JSON type when available, otherwise stores as Text with JSON serialization.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            import json
            if dialect.name != "postgresql":
                return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if dialect.name != "postgresql":
                import json
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
        return value

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSON as PG_JSON
            return dialect.type_descriptor(PG_JSON())
        return dialect.type_descriptor(Text())
