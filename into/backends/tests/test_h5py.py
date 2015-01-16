from __future__ import absolute_import, division, print_function

from into.backends.h5py import (append, create, resource, discover, convert,
        resource_h5py)
from contextlib import contextmanager
from into.utils import tmpfile
from into.chunks import iterable
from into import into, append, convert, discover
import datashape
import h5py
import numpy as np
import os


@contextmanager
def file(x):
    with tmpfile('.hdf5') as fn:
        f = h5py.File(fn)
        data = f.create_dataset('/data', data=x, chunks=True,
                                maxshape=(None,) + x.shape[1:])

        try:
            yield fn, f, data
        finally:
            f.close()


x = np.ones((2, 3), dtype='i4')


def test_discover():
    with file(x) as (fn, f, dset):
        assert str(discover(dset)) == str(discover(x))
        assert str(discover(f)) == str(discover({'data': x}))


def eq(a, b):
    c = a == b
    if isinstance(c, np.ndarray):
        c = c.all()
    return c


def test_append():
    with file(x) as (fn, f, dset):
        append(dset, x)
        assert eq(dset[:], np.concatenate([x, x]))


def test_into_resource():
    with tmpfile('.hdf5') as fn:
        d = into(fn+'::/x', x)
        assert d.shape == x.shape
        assert eq(d[:], x[:])


def test_numpy():
    with file(x) as (fn, f, dset):
        assert eq(convert(np.ndarray, dset), x)


def test_chunks():
    with file(x) as (fn, f, dset):
        c = convert(iterable(np.ndarray), dset)
        assert eq(convert(np.ndarray, c), x)


def test_append_chunks():
    with file(x) as (fn, f, dset):
        append(dset, iterable(np.ndarray)([x, x]))

        assert len(dset) == len(x) * 3


def test_create():
    with tmpfile('.hdf5') as fn:
        ds = datashape.dshape('{x: int32, y: {z: 3 * int32}}')
        f = create(h5py.File, dshape='{x: int32, y: {z: 3 * int32}}', path=fn)
        assert isinstance(f, h5py.File)
        assert f.filename == fn
        assert discover(f) == ds


def test_create_partially_present_dataset():
    with tmpfile('.hdf5') as fn:
        ds1 = datashape.dshape('{x: int32}')
        f = create(h5py.File, dshape=ds1, path=fn)

        ds2 = datashape.dshape('{x: int32, y: 5 * int32}')
        f2 = create(h5py.File, dshape=ds2, path=fn)

        assert f.filename == f2.filename
        assert list(f.keys()) == list(f2.keys())
        assert f['y'].dtype == 'i4'


def test_resource():
    with tmpfile('.hdf5') as fn:
        ds = datashape.dshape('{x: int32, y: 3 * int32}')
        r = resource(fn, dshape=ds)

        assert isinstance(r, h5py.File)
        assert discover(r) == ds

        r2 = resource(fn + '::/x')
        assert isinstance(r2, h5py.Dataset)


def test_resource_with_datapath():
    with tmpfile('.hdf5') as fn:
        ds = datashape.dshape('3 * 4 * int32')
        r = resource(fn + '::/data', dshape=ds)

        assert isinstance(r, h5py.Dataset)
        assert discover(r) == ds
        assert r.file.filename == fn
        assert r.file['/data'] == r


def test_resource_with_variable_length():
    with tmpfile('.hdf5') as fn:
        ds = datashape.dshape('var * 4 * int32')
        r = resource(fn + '::/data', dshape=ds)

        assert r.shape == (0, 4)


def test_copy_with_into():
    with tmpfile('.hdf5') as fn:
        dset = into(fn + '::/data', [1, 2, 3])
        assert dset.shape == (3,)
        assert eq(dset[:], [1, 2, 3])


def test_varlen_dtypes():
    y = np.array([('Alice', 100), ('Bob', 200)],
                dtype=[('name', 'O'), ('amount', 'i4')])
    with tmpfile('.hdf5') as fn:
        dset = into(fn + '::/data', y)

        assert into(list, dset) == into(list, dset)


def test_resource_shape():
    with tmpfile('.hdf5') as fn:
        assert resource(fn+'::/data', dshape='10 * int').shape == (10,)
    with tmpfile('.hdf5') as fn:
        assert resource(fn+'::/data', dshape='10 * 10 * int').shape == (10, 10)
    with tmpfile('.hdf5') as fn:
        assert resource(fn+'::/data', dshape='var * 10 * int').shape == (0, 10)
