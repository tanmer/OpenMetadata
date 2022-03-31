#  Copyright 2021 Collate
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import enum

from clickhouse_sqlalchemy.drivers.base import ClickHouseDialect
from clickhouse_sqlalchemy.drivers.http.transport import RequestsTransport, _get_type
from clickhouse_sqlalchemy.drivers.http.utils import parse_tsv
from sqlalchemy import exc, schema, text
from sqlalchemy import types as sqltypes
from sqlalchemy import util as sa_util
from sqlalchemy.engine import reflection
from sqlalchemy.util import warn

from metadata.ingestion.ometa.openmetadata_rest import MetadataServerConfig
from metadata.ingestion.source.sql_source import SQLSource
from metadata.ingestion.source.sql_source_common import SQLConnectionConfig


@reflection.cache
def _get_column_type(self, name, spec):
    if spec.startswith("Array"):
        inner = spec[6:-1]
        coltype = self.ischema_names["_array"]
        return coltype(self._get_column_type(name, inner))

    elif spec.startswith("FixedString"):
        return self.ischema_names["FixedString"]

    elif spec.startswith("Nullable"):
        inner = spec[9:-1]
        coltype = self.ischema_names["_nullable"]
        return self._get_column_type(name, inner)

    elif spec.startswith("LowCardinality"):
        inner = spec[15:-1]
        coltype = self.ischema_names["_lowcardinality"]
        return coltype(self._get_column_type(name, inner))

    elif spec.startswith("Tuple"):
        inner = spec[6:-1]
        coltype = self.ischema_names["_tuple"]
        inner_types = [self._get_column_type(name, t.strip()) for t in inner.split(",")]
        return coltype(*inner_types)

    elif spec.startswith("Map"):
        inner = spec[4:-1]
        coltype = self.ischema_names["_map"]
        inner_types = [self._get_column_type(name, t.strip()) for t in inner.split(",")]
        return coltype(*inner_types)

    elif spec.startswith("Enum"):
        pos = spec.find("(")
        type = spec[:pos]
        coltype = self.ischema_names[type]

        options = dict()
        if pos >= 0:
            options = self._parse_options(spec[pos + 1 : spec.rfind(")")])
        if not options:
            return sqltypes.NullType

        type_enum = enum.Enum("%s_enum" % name, options)
        return lambda: coltype(type_enum)

    elif spec.startswith("DateTime64"):
        return self.ischema_names["DateTime64"]

    elif spec.startswith("DateTime"):
        return self.ischema_names["DateTime"]

    elif spec.startswith("IP"):
        return self.ischema_names["String"]

    elif spec.lower().startswith("decimal"):
        coltype = self.ischema_names["Decimal"]
        return coltype(*self._parse_decimal_params(spec))
    else:
        try:
            return self.ischema_names[spec]
        except KeyError:
            warn("Did not recognize type '%s' of column '%s'" % (spec, name))
            return sqltypes.NullType


def execute(self, query, params=None):
    """
    Query is returning rows and these rows should be parsed or
    there is nothing to return.
    """
    r = self._send(query, params=params, stream=True)
    lines = r.iter_lines()
    try:
        names = parse_tsv(next(lines), self.unicode_errors)
        types = parse_tsv(next(lines), self.unicode_errors)
    except StopIteration:
        # Empty result; e.g. a DDL request.
        return

    convs = [_get_type(type_) for type_ in types if type_]

    yield names
    yield types

    for line in lines:
        yield [
            (conv(x) if conv else x)
            for x, conv in zip(parse_tsv(line, self.unicode_errors), convs)
        ]


@reflection.cache
def get_unique_constraints(self, connection, table_name, schema=None, **kw):
    return []


@reflection.cache
def get_pk_constraint(self, bind, table_name, schema=None, **kw):
    return {"constrained_columns": [], "name": "undefined"}


@reflection.cache
def get_table_comment(self, connection, table_name, schema=None, **kw):
    return {"text": None}


ClickHouseDialect.get_unique_constraints = get_unique_constraints
ClickHouseDialect.get_pk_constraint = get_pk_constraint
ClickHouseDialect._get_column_type = _get_column_type
ClickHouseDialect.get_table_comment = get_table_comment
RequestsTransport.execute = execute

from metadata.generated.schema.entity.services.connections.database.clickhouseConnection import (
    ClickhouseConnection,
)


class ClickhouseConfig(ClickhouseConnection, SQLConnectionConfig):
    def get_connection_url(self):
        return super().get_connection_url()


class ClickhouseSource(SQLSource):
    def __init__(self, config, metadata_config, ctx):
        super().__init__(config, metadata_config, ctx)

    @classmethod
    def create(cls, config_dict, metadata_config_dict, ctx):
        config = ClickhouseConfig.parse_obj(config_dict)
        metadata_config = MetadataServerConfig.parse_obj(metadata_config_dict)
        return cls(config, metadata_config, ctx)
