"""
Varsha — Portable geometry column type.

Production runs on PostgreSQL + PostGIS, where boundaries are stored as real
`geometry(MULTIPOLYGON, 4326)` columns with a GiST index. Local development,
tests and the offline demo run on SQLite, where the same column is plain text.

On both backends the Python side of the column is a GeoJSON geometry dict:
    block.geometry = {"type": "Polygon", "coordinates": [...]}
    block.geometry  -> {"type": "MultiPolygon", ...}   (PostGIS normalises)
"""

import json

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import Text, TypeDecorator, UserDefinedType


class _PostGISGeometry(UserDefinedType):
    """DDL-only PostGIS geometry type (no geoalchemy2 dependency)."""

    cache_ok = True

    def __init__(self, geometry_type: str = "MULTIPOLYGON", srid: int = 4326):
        self.geometry_type = geometry_type
        self.srid = srid

    def get_col_spec(self, **kw):
        return f"geometry({self.geometry_type}, {self.srid})"


class _GeomFromGeoJSON(FunctionElement):
    inherit_cache = True
    type = Text()


class _GeoJSONText(TypeDecorator):
    """Result type of the read expression: GeoJSON text -> dict."""

    impl = Text
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, (dict, list)):
            return value
        return json.loads(value)


class _GeomAsGeoJSON(FunctionElement):
    inherit_cache = True
    type = _GeoJSONText()


@compiles(_GeomFromGeoJSON)
def _from_geojson_default(element, compiler, **kw):
    return compiler.process(element.clauses, **kw)


@compiles(_GeomFromGeoJSON, "postgresql")
def _from_geojson_pg(element, compiler, **kw):
    arg = compiler.process(element.clauses, **kw)
    return f"ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(CAST({arg} AS TEXT)), 4326))"


@compiles(_GeomAsGeoJSON)
def _as_geojson_default(element, compiler, **kw):
    return compiler.process(element.clauses, **kw)


@compiles(_GeomAsGeoJSON, "postgresql")
def _as_geojson_pg(element, compiler, **kw):
    return f"ST_AsGeoJSON({compiler.process(element.clauses, **kw)}, 6)"


class GeoJSONGeometry(TypeDecorator):
    """Geometry column: PostGIS geometry on PostgreSQL, GeoJSON text elsewhere."""

    impl = Text
    cache_ok = True

    def __init__(self, geometry_type: str = "MULTIPOLYGON", srid: int = 4326):
        super().__init__()
        self.geometry_type = geometry_type
        self.srid = srid

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PostGISGeometry(self.geometry_type, self.srid))
        return dialect.type_descriptor(Text())

    def bind_expression(self, bindvalue):
        return _GeomFromGeoJSON(bindvalue)

    def column_expression(self, col):
        return _GeomAsGeoJSON(col)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)
