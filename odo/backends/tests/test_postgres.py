from __future__ import absolute_import, division, print_function

import pytest

sa = pytest.importorskip('sqlalchemy')
pytest.importorskip('psycopg2')

import os
import itertools

from datashape import dshape

from odo.backends.csv import CSV
from odo import odo, into, resource, drop, discover
from odo.utils import assert_allclose, tmpfile


names = ('tbl%d' % i for i in itertools.count())
new_schema = object()
data = [(1, 2), (10, 20), (100, 200)]
null_data = [(1, None), (10, 20), (100, 200)]


@pytest.yield_fixture(scope='module')
def csv():
    with tmpfile('.csv') as fn:
        with open(fn, 'w') as f:
            f.write('\n'.join(','.join(map(str, row)) for row in data))
        yield CSV(fn)


@pytest.fixture
def complex_csv():
    this_dir = os.path.dirname(__file__)
    return CSV(os.path.join(this_dir, 'dummydata.csv'), has_header=True)


@pytest.fixture
def url():
    return 'postgresql://postgres@localhost/test::%s' % next(names)


def sql_fixture(dshape, schema=None):
    @pytest.yield_fixture(params=(True, False))
    def fixture(request, url):
        try:
            t = resource(
                url,
                dshape=dshape,
                schema=next(names) if schema is new_schema else schema,
            )
        except sa.exc.OperationalError as e:
            pytest.skip(str(e))
        else:
            try:
                bind = t.bind
                if not request.param:
                    t.metadata.bind = None
                yield t, bind
            finally:
                t.metadata.bind = bind
                drop(t)
                if t.schema is not None:
                    bind.execute(sa.sql.ddl.DropSchema(t.schema))

    return fixture


sql = sql_fixture('var * {a: int32, b: ?int32}')
sql_with_schema = sql_fixture('var * {a: int32, b: ?int32}', new_schema)
sql_with_ugly_schema = sql_fixture('var * {a: int32, b: ?int32}', 'foo.b.ar')
complex_sql = sql_fixture("""
    var * {
        Name: string, RegistrationDate: date, ZipCode: int32, Consts: float64
    }
""")
sql_with_array = sql_fixture('var * {a: var * float64, b: string}', 'public')


def test_simple_into(csv, sql):
    sql, bind = sql
    into(sql, csv, dshape=discover(sql), bind=bind)
    assert into(list, sql, bind=bind) == data


def test_append(csv, sql):
    sql, bind = sql
    into(sql, csv, bind=bind)
    assert into(list, sql, bind=bind) == data

    into(sql, csv, bind=bind)
    assert into(list, sql, bind=bind) == data + data


def test_tryexcept_into(csv, sql):
    sql, bind = sql
    with pytest.raises(sa.exc.NotSupportedError):
        into(sql, csv, quotechar="alpha", bind=bind)  # uses multi-byte character


def test_no_header_no_columns(csv, sql):
    sql, bind = sql
    into(sql, csv, bind=bind, dshape=discover(sql))
    assert into(list, sql, bind=bind) == data


def test_complex_into(complex_csv, complex_sql):
    complex_sql, bind = complex_sql
    # data from: http://dummydata.me/generate
    into(complex_sql, complex_csv, dshape=discover(complex_sql), bind=bind)
    assert_allclose(into(list, complex_sql, bind=bind), into(list, complex_csv))


def test_sql_to_csv(sql, csv):
    sql, bind = sql
    sql = odo(csv, sql, bind=bind)
    with tmpfile('.csv') as fn:
        csv = odo(sql, fn, bind=bind)
        assert odo(csv, list) == data
        assert discover(csv).measure.names == discover(sql).measure.names


def test_sql_select_to_csv(sql, csv):
    sql, bind = sql
    sql = odo(csv, sql, bind=bind)
    query = sa.select([sql.c.a])
    with tmpfile('.csv') as fn:
        csv = odo(query, fn, bind=bind)
        assert odo(csv, list) == [(x,) for x, _ in data]


def test_invalid_escapechar(sql, csv):
    sql, bind = sql
    with pytest.raises(ValueError):
        odo(csv, sql, escapechar='12', bind=bind)

    with pytest.raises(ValueError):
        odo(csv, sql, escapechar='', bind=bind)


def test_csv_output_is_not_quoted_by_default(sql, csv):
    sql, bind = sql
    sql = odo(csv, sql, bind=bind)
    expected = "a,b\n1,2\n10,20\n100,200\n"
    with tmpfile('.csv') as fn:
        csv = odo(sql, fn, bind=bind)
        with open(fn, 'rt') as f:
            result = f.read()
        assert result == expected


def test_na_value(sql, csv):
    sql, bind = sql
    sql = odo(null_data, sql, bind=bind)
    with tmpfile('.csv') as fn:
        csv = odo(sql, fn, na_value='NA', bind=bind)
        with open(csv.path, 'rt') as f:
            raw = f.read()
    assert raw == 'a,b\n1,NA\n10,20\n100,200\n'


def test_different_encoding(url):
    encoding = 'latin1'
    path = os.path.join(os.path.dirname(__file__), 'encoding.csv')
    try:
        sql = odo(path, url, encoding=encoding)
    except sa.exc.OperationalError as e:
        pytest.skip(str(e))
    else:
        try:
            result = odo(sql, list)
            expected = [(u'1958.001.500131-1A', 1, None, u'', 899),
                        (u'1958.001.500156-6', 1, None, u'', 899),
                        (u'1958.001.500162-1', 1, None, u'', 899),
                        (u'1958.001.500204-2', 1, None, u'', 899),
                        (u'1958.001.500204-2A', 1, None, u'', 899),
                        (u'1958.001.500204-2B', 1, None, u'', 899),
                        (u'1958.001.500223-6', 1, None, u'', 9610),
                        (u'1958.001.500233-9', 1, None, u'', 4703),
                        (u'1909.017.000018-3', 1, 30.0, u'sumaria', 899)]
            assert result == expected
        finally:
            drop(sql)


def test_schema(csv, sql_with_schema):
    sql_with_schema, bind = sql_with_schema
    assert odo(odo(csv, sql_with_schema, bind=bind), list, bind=bind) == data


def test_ugly_schema(csv, sql_with_ugly_schema):
    sql_with_ugly_schema, bind = sql_with_ugly_schema
    assert (
        odo(odo(csv, sql_with_ugly_schema, bind=bind), list, bind=bind) ==
        data
    )


def test_schema_discover(sql_with_schema):
    sql_with_schema, bind = sql_with_schema
    sql_with_schema.metadata.bind = bind
    meta = discover(sql_with_schema.metadata)
    assert meta == dshape('{%s: var * {a: int32, b: ?int32}}' %
                          sql_with_schema.name)


def test_discover_array(sql_with_array):
    sql, bind = sql_with_array
    expected = dshape('var * {a: var * float64, b: string}')
    result = discover(sql)
    assert result == expected


def test_nested_records_fail(url):
    with pytest.raises(TypeError):
        resource(url, dshape='var * {a: var * float64, b: {c: int64}}')
