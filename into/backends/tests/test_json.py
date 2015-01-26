from into.backends.json import *
from into.utils import tmpfile
from into import into
from contextlib import contextmanager
from datashape import dshape
import datetime
import json

@contextmanager
def json_file(data):
    with tmpfile('.json') as fn:
        with open(fn, 'w') as f:
            json.dump(data, f, default=json_dumps)

        yield fn

@contextmanager
def jsonlines_file(data):
    with tmpfile('.json') as fn:
        with open(fn, 'w') as f:
            for item in data:
                json.dump(item, f, default=json_dumps)
                f.write('\n')

        yield fn


dat = [{'name': 'Alice', 'amount': 100},
       {'name': 'Bob', 'amount': 200}]

def test_discover_json():
    with json_file(dat) as fn:
        j = JSON(fn)
        assert discover(j) == discover(dat)

def test_discover_jsonlines():
    with jsonlines_file(dat) as fn:
        j = JSONLines(fn)
        assert discover(j) == discover(dat)


def test_discover_json_only_includes_datetimes_not_dates():
    data = [{'name': 'Alice', 'dt': datetime.date(2002, 2, 2)},
            {'name': 'Bob',   'dt': datetime.date(2000, 1, 1)}]
    with json_file(data) as fn:
        j = JSON(fn)
        assert discover(j) == dshape('2 * {dt: datetime, name: string }')


def test_resource():
    assert isinstance(resource('jsonlines://foo.json'), JSONLines)
    assert isinstance(resource('json://foo.json'), JSON)

    assert isinstance(resource('foo.json', expected_dshape=dshape('var * {a: int}')),
                      JSONLines)

def test_resource_guessing():
    with json_file(dat) as fn:
        assert isinstance(resource(fn), JSON)

    with jsonlines_file(dat) as fn:
        assert isinstance(resource(fn), JSONLines)


def test_append_jsonlines():
    with tmpfile('json') as fn:
        j = JSONLines(fn)
        append(j, dat)
        with open(j.path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert 'Alice' in lines[0]
        assert 'Bob' in lines[1]


def test_append_json():
    with tmpfile('json') as fn:
        j = JSON(fn)
        append(j, dat)
        with open(j.path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        assert 'Alice' in lines[0]
        assert 'Bob' in lines[0]


def test_convert_json_list():
    with json_file(dat) as fn:
        j = JSON(fn)
        assert convert(list, j) == dat


def test_convert_jsonlines():
    with jsonlines_file(dat) as fn:
        j = JSONLines(fn)
        assert convert(list, j) == dat


def test_tuples_to_json():
    ds = dshape('var * {a: int, b: int}')
    with tmpfile('json') as fn:
        j = JSON(fn)

        append(j, [(1, 2), (10, 20)], dshape=ds)
        with open(fn) as f:
            assert '"a": 1' in f.read()

    with tmpfile('json') as fn:
        j = JSONLines(fn)

        append(j, [(1, 2), (10, 20)], dshape=ds)
        with open(fn) as f:
            assert '"a": 1' in f.read()


def test_datetimes():
    from into import into
    import numpy as np
    data = [{'a': 1, 'dt': datetime.datetime(2001, 1, 1)},
            {'a': 2, 'dt': datetime.datetime(2002, 2, 2)}]
    with tmpfile('json') as fn:
        j = JSONLines(fn)
        append(j, data)

        assert str(into(np.ndarray, j)) == str(into(np.ndarray, data))


def test_json_encoder():
    result = json.dumps([1, datetime.datetime(2000, 1, 1, 12, 30, 0)],
                       default=json_dumps)
    assert result == '[1, "2000-01-01T12:30:00Z"]'
    assert json.loads(result) == [1, "2000-01-01T12:30:00Z"]


def test_empty_line():
    text = '{"a": 1}\n{"a": 2}\n\n'  # extra endline
    with tmpfile('.json') as fn:
        with open(fn, 'w') as f:
            f.write(text)
        j = JSONLines(fn)
        assert len(convert(list, j)) == 2
