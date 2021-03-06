from astatsa.utils import show_some
from contracts import new_contract, contract
import numpy as np
from .misc_utils import coords_iterate


__all__ = ['valid_diffeomorphism',
            'diffeo_identity',
            'coords_to_X',
            'X_to_coords',
            'diffeo_compose',
            'diffeo_apply',
            'diffeo_local_differences',
            'diffeo_local_differences_L2',
            'diffeo_distance_Linf',
            'diffeo_distance_L2',
            'diffeo_norm_L2',
            'dmod',
            'diffeo_inverse',
            'diffeo_from_function',
            'diffeomorphism_from_function']



@new_contract
# @contract(x='array[MxNx2](int32|float32)')
@contract(x='array[MxNx2]')
def valid_diffeomorphism(x):
    M, N = x.shape[0], x.shape[1]
    
    c = [
         ('0 <= x[:, :, 0]', x[:, :, 0], lambda y: 0 <= y),
         ('x[:, :, 0] < %s' % M, x[:, :, 0], lambda y: y < M),
         ('0 <= x[:, :, 1]', x[:, :, 1], lambda y: 0 <= y),
         ('x[:, :, 1] < %s' % N, x[:, :, 1], lambda y: y < N),
    ]
    
    m = ''
    for condition, x, check in c:
        checks = check(x)
        if not np.all(checks):
            m += show_some(x, np.logical_not(checks), condition, MAX_N=4) + '\n'
            
    if m:
        raise ValueError(m)
    
@contract(shape='valid_2d_shape', returns='valid_diffeomorphism')
def diffeo_identity(shape):
    M = shape[0]
    N = shape[1]
    d = np.zeros((M, N, 2), 'int32')
    for i, j in coords_iterate(shape):
        d[i, j, 0] = i
        d[i, j, 1] = j
    return d

diffeomorphism_identity = diffeo_identity


def coords_to_X(c, shape):
    """ Maps cell coordinates to [(-1,1),(-1,1)] coordinates. """
    a, b = c
    assert 0 <= a <= shape[0]
    assert 0 <= b <= shape[1]
    a = float(a)
    b = float(b)
    a = a + 0.5  # center cells
    b = b + 0.5
    u = a / (shape[0])
    v = b / (shape[1])
    x = 2 * (u - 0.5)
    y = 2 * (v - 0.5)
    assert -1 <= x <= +1
    assert -1 <= y <= +1
    return (x, y)


def X_to_coords(X, shape):
    """ Inverse of coords_to_X """
    x, y = X
    assert -1 <= x <= +1, 'outside bounds: %s' % x
    assert -1 <= y <= +1, 'outside bounds: %s' % y
    a = np.round((x / 2 + 0.5) * (shape[0] - 1))
    b = np.round((y / 2 + 0.5) * (shape[1] - 1))
    a = int(a)
    b = int(b)
    assert 0 <= a <= shape[0]
    assert 0 <= b <= shape[1]
    return (a, b)


@contract(shape='valid_2d_shape', returns='valid_diffeomorphism')
def diffeo_from_function(shape, f):
    ''' 
        This creates a diffeomorphism from a function f
        from =[-1,1]x[-1,1] to itself:
        
          f : [-1,1]x[-1,1] -> [-1,1]x[-1,1]   
    '''

    M = shape[0]
    N = shape[1]
    D = np.zeros((M, N, 2), dtype='int32')
    for coords in coords_iterate(shape):
        X = coords_to_X(coords, shape)
        Y = f(X)
        a, b = X_to_coords(Y, shape)
        D[coords[0], coords[1], :] = [a, b]
    return D

diffeomorphism_from_function = diffeo_from_function


@contract(a='valid_diffeomorphism,array[MxNx2]',
          b='valid_diffeomorphism,array[MxNx2]',
          returns='valid_diffeomorphism,array[MxNx2]')
def diffeo_compose(a, b):
    """ Composition of two diffeomorphisms. """
    c = np.empty_like(a)
    c[:, :, 0] = diffeo_apply(b, a[:, :, 0])
    c[:, :, 1] = diffeo_apply(b, a[:, :, 1])
    return c


@contract(a='valid_diffeomorphism,array[MxNx2]',
          returns='valid_diffeomorphism,array[MxNx2]')
def diffeo_inverse(a):
    """ 
        Inverse of a diffeomorphism; this is a very, very not well 
        conditioned operation to do. We avoid it and estimate the 
        inverse as well. 
    """
    M, N = a.shape[0], a.shape[1]
    result = np.empty_like(a)
    result.fill(-1)  # fill invalid data
    many = np.zeros((M, N))
    many.fill(0)
    for i, j in coords_iterate((M, N)):
        i1 = a[i, j, 0]
        j1 = a[i, j, 1]
        result[i1, j1, 0] = i
        result[i1, j1, 1] = j
        many[i1, j1] += 1

    num = (many == 0).sum()
    if num:
        fill_invalid(result[:, :, 0], -1)
        fill_invalid(result[:, :, 1], -1)

    return result


def fill_invalid(x, invalid_value):
    i, j = np.nonzero(x == invalid_value)
    coords = [np.array(s) for s in zip(i, j)]
    while coords:
        # extract random coordinates
        c = coords.pop(np.random.randint(len(coords)))
        options = []
        for d in [[-1, 0], [+1, 0], [0, 1], [0, -1]]:
            c2 = tuple(np.mod(c + d, x.shape).astype('int'))
            if x[c2] != invalid_value:
                options.append(x[c2])

        if not options:
            coords.append(c)
        else:
            x[tuple(c)] = most_frequent(options)


def most_frequent(a):
    return max(map(lambda val: (a.count(val), val), set(a)))[-1]


@contract(diffeo='valid_diffeomorphism,array[MxNx2]',
          template='array[MxNx...]')
def diffeo_apply(diffeo, template):
    """ diffeo is a diffeomoprhims, and template is an image,
        returns diffeo(template) 
    """
    M, N = diffeo.shape[0], diffeo.shape[1]
    result = np.empty_like(template)
    for i, j in coords_iterate((M, N)):
        i1 = diffeo[i, j, 0]
        j1 = diffeo[i, j, 1]
        result[i, j, ...] = template[i1, j1, ...]
    return result


@contract(a='valid_diffeomorphism,array[MxNx2]',
          b='valid_diffeomorphism,array[MxNx2]',
          returns='tuple(array[MxN](float32), array[MxN](float32))')
def diffeo_local_differences(a, b):
    ''' returns tuple (x,y) with normalized difference fields.
        Each entry is normalized in [-0.5,0.5]  '''
    diff = a - b    
    # XXX: fixed torus topology
    diffmod0 = dmod(diff[:, :, 0], a.shape[0] / 2) 
    diffmod1 = dmod(diff[:, :, 1], a.shape[1] / 2)    
    M, N = a.shape[:2]
    x = np.empty((M, N), 'float32')
    y = np.empty((M, N), 'float32')
    np.multiply(diffmod0, 1.0 / a.shape[0], out=x)
    np.multiply(diffmod1, 1.0 / a.shape[1], out=y)
    return x, y

@contract(a='valid_diffeomorphism,array[MxNx2]',
          b='valid_diffeomorphism,array[MxNx2]',
          returns='array[MxN](float32)')
def diffeo_local_differences_L2(a, b):
    ''' Returns the norm of the difference between the two diffeos, pointwise. '''
    dx, dy = diffeo_local_differences(a, b)
    norm = np.hypot(dx, dy)
    return norm


@contract(a='valid_diffeomorphism,array[MxNx2]',
          b='valid_diffeomorphism,array[MxNx2]',
          returns='>=0,<=0.5')
def diffeo_distance_Linf(a, b):
    ''' 
        Computes the distance between two diffeomorphism.
        This is the maximum difference between the two. 
        The minimum is 0 (of course);
        the maximum is 0.5.
    '''
    x, y = diffeo_local_differences(a, b)
    dx = np.abs(x).max()
    dy = np.abs(y).max()
    return float(np.max(dx, dy))


@contract(a='valid_diffeomorphism,array[MxNx2]',
          b='valid_diffeomorphism,array[MxNx2]',
          returns='>=0,<0.71')
def diffeo_distance_L2(a, b):
    ''' The maximum is sqrt(0.5**2 + 0.5**2) = sqrt(0.5)
        = sqrt(1/2) = sqrt(2)/2 '''
    x, y = diffeo_local_differences(a, b)
    dist = np.sqrt(x * x + y * y)
    return float(dist.mean())


@contract(a='valid_diffeomorphism', returns='>=0, <0.71')
def diffeo_norm_L2(a):
    ''' The norm is the distance from the identity. '''
    # TODO: unittests
    b = diffeo_identity((a.shape[0], a.shape[1]))
    return diffeo_distance_L2(a, b)


# def dmod(x, N):
#    ''' Normalizes between [-N, +N-1] '''
#    out = x.copy()
#    out += N
#    np.mod(out, 2 * N, out)
#    out -= N
#    return out

def dmod(x, N):
    ''' Normalizes between [-N, +N-1] '''
    return ((x + N) % (2 * N)) - N

