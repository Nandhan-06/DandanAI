from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


class EmbeddingType(TypeDecorator):
    """pgvector `vector(N)` on PostgreSQL/Neon. JSON only under the ephemeral test database."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(get_settings().embedding_dim))
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value, dialect):
        return None if value is None else [float(x) for x in value]
