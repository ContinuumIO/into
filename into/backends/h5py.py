from __future__ import absolute_import, division, print_function

import datashape
from datashape import (DataShape, Record, Mono, dshape, to_numpy,
        to_numpy_dtype, discover)
from datashape.predicates import isrecord, iscollection
from datashape.dispatch import dispatch
import h5py
import numpy as np
from toolz import assoc, keyfilter
from collections import Iterator

from ..append import append
from ..convert import convert, ooc_types
from ..create import create
from ..resource import resource, resource_matches
from ..chunks import chunks, Chunks
from ..compatibility import unicode
from into.backends.hdf import HDFFile, HDFTable

h5py_attributes = ['chunks', 'compression', 'compression_opts', 'dtype',
                   'fillvalue', 'fletcher32', 'maxshape', 'shape']


@discover.register((h5py.Group, h5py.File))
def discover_h5py_group_file(g):
    return DataShape(Record([[k, discover(v)] for k, v in g.items()]))


@discover.register(h5py.Dataset)
def discover_h5py_dataset(d):
    s = str(datashape.from_numpy(d.shape, d.dtype))
    return dshape(s.replace('object', 'string'))


def varlen_dtype(dt):
    """ Inject variable length string element for 'O' """
    if "'O'" not in str(dt):
        return dt
    varlen = h5py.special_dtype(vlen=unicode)
    return np.dtype(eval(str(dt).replace("'O'", 'varlen')))


def dataset_from_dshape(file, datapath, ds, **kwargs):
    dtype = varlen_dtype(to_numpy_dtype(ds))
    if datashape.var not in list(ds):
        shape = to_numpy(ds)[0]
    elif datashape.var not in list(ds)[1:]:
        shape = (0,) + to_numpy(ds.subshape[0])[0]
    else:
        raise ValueError("Don't know how to handle varlen nd shapes")

    if shape:
        kwargs['chunks'] = kwargs.get('chunks', True)
        kwargs['maxshape'] = kwargs.get('maxshape', (None,) + shape[1:])

    kwargs2 = keyfilter(h5py_attributes.__contains__, kwargs)
    return file.require_dataset(datapath, shape=shape, dtype=dtype, **kwargs2)


def create_from_datashape(group, ds, name=None, **kwargs):
    assert isrecord(ds)
    if isinstance(ds, DataShape) and len(ds) == 1:
        ds = ds[0]
    for name, sub_ds in ds.dict.items():
        if isrecord(sub_ds):
            g = group.require_group(name)
            create_from_datashape(g, sub_ds, **kwargs)
        else:
            dataset_from_dshape(file=group.file,
                                datapath='/'.join([group.name, name]),
                                ds=sub_ds, **kwargs)


@create.register(h5py.File)
def create_h5py_file(cls, path=None, dshape=None, **kwargs):
    f = h5py.File(path)
    create_from_datashape(f, dshape, **kwargs)
    return HDFFile(f)


@append.register(h5py.Dataset, np.ndarray)
def append_h5py(dset, x, **kwargs):
    if not sum(x.shape):
        return dset
    shape = list(dset.shape)
    shape[0] += len(x)
    dset.resize(shape)
    dset[-len(x):] = x
    return dset


@append.register(h5py.Dataset, chunks(np.ndarray))
def append_h5py(dset, c, **kwargs):
    for chunk in c:
        append(dset, chunk)
    return dset


@append.register(h5py.Dataset, object)
def append_h5py(dset, x, **kwargs):
    return append(dset, convert(chunks(np.ndarray), x, **kwargs), **kwargs)


@convert.register(np.ndarray, h5py.Dataset, cost=3.0)
def h5py_to_numpy(dset, force=False, **kwargs):
    if dset.size > 1e9:
        raise MemoryError("File size is large: %0.2f GB.\n"
                          "Convert with flag force=True to force loading" %
                          dset.size / 1e9)
    else:
        return dset[:]


@convert.register(chunks(np.ndarray), h5py.Dataset, cost=3.0)
def h5py_to_numpy_chunks(t, chunksize=2 ** 20, **kwargs):
    return chunks(np.ndarray)(h5py_to_numpy_iterator(t, chunksize=chunksize, **kwargs))

@convert.register(Iterator, h5py.Dataset, cost=5.0)
def h5py_to_numpy_iterator(t, chunksize=1e7, **kwargs):
    """ return the embedded iterator """
    chunksize = int(chunksize)
    for i in range(0, t.shape[0], chunksize):
        yield t[i: i + chunksize]

@resource.register('^(h5py://)?.+\.(h5|hdf5)', priority=10.0)
def resource_h5py(uri, datapath=None, dshape=None, **kwargs):

    uri = resource_matches(uri, 'h5py')

    olddatapath = datapath

    if dshape is not None:
        ds = datashape.dshape(dshape)
        if datapath is not None:
            while ds and datapath:
                datapath, name = datapath.rsplit('/', 1)
                ds = Record([[name, ds]])
            ds = datashape.dshape(ds)
        f = create(h5py.File, path=uri, dshape=ds, **kwargs)
    else:
        f = h5py.File(uri)
        ds = discover(f)

    if olddatapath is not None:
        return HDFTable(HDFFile(f), olddatapath)

    return HDFFile(f)


@dispatch((h5py.Group, h5py.Dataset))
def drop(h):
    del h.file[h.name]

@dispatch(h5py.File)
def drop(h):
    cleanup(h)
    os.remove(h.filename)

# hdf resource impl
@dispatch(h5py.File)
def pathname(f):
    return f.filename

@dispatch(h5py.File)
def dialect(f):
    return 'h5py'

@dispatch(h5py.File)
def get_table(f, datapath):
    assert datapath is not None
    return f[datapath]

@dispatch(h5py.File, object)
def open_handle(f, pathname):
    try:
        f.close()
    except:
        pass
    return h5py.File(pathname)

@dispatch(h5py.File)
def cleanup(f):
    f.close()

@dispatch(h5py.Dataset)
def cleanup(dset):
    dset.file.close()

ooc_types.add(h5py.Dataset)
