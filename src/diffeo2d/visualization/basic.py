from ..stats import diffeo_stats
from contracts import contract
from reprep import posneg, scale
import itertools
import numpy as np

__all__ = ['diffeomorphism_to_rgb', 'diffeomorphism_to_rgb_cont',
           'diffeo_to_rgb_norm', 'diffeo_to_rgb_angle',
           'angle_legend', 'diffeo_to_rgb_inc', 'diffeo_to_rgb_curv']

@contract(D='valid_diffeomorphism')
def diffeomorphism_to_rgb(D, nquads=15):
    ''' Displays a diffeomorphism as an RGB image. '''
    M, N = D.shape[0], D.shape[1]
    side = int(np.ceil(M * 1.0 / nquads))
    rgb = np.zeros((M, N, 3), 'uint8')

    rgb[:, :, 0] = ((D[:, :, 0] / side) % 2) * 255
    # rgb[:, :, 1] = (D[:, :, 0] * 120) / M + (D[:, :, 1] * 120) / N
    rgb[:, :, 1] = 0
    rgb[:, :, 2] = ((D[:, :, 1] / side) % 2) * 255

    return rgb


@contract(D='valid_diffeomorphism')
def diffeomorphism_to_rgb_cont(D):
    M, N = D.shape[0], D.shape[1]
    n = 3
    rgb = np.zeros((M, N, 3), 'uint8')
    rgb[:, :, 0] = (D[:, :, 0] * n * 255) / M
    rgb[:, :, 1] = 100
    rgb[:, :, 2] = (D[:, :, 1] * n * 255) / N
    return rgb


@contract(D='valid_diffeomorphism')
def diffeo_to_rgb_norm(D, max_value=None):
    stats = diffeo_stats(D)
    return scale(stats.norm, min_value=0, max_value=max_value,
                 min_color=[1, 1, 1],
                 max_color=[0, 0, 1])


@contract(D='valid_diffeomorphism', returns='array[HxWx3](uint8)')
def diffeo_to_rgb_angle(D):
    stats = diffeo_stats(D)
    zero_norm = stats.norm == 0
    angle = stats.angle.copy()
    angle[zero_norm] = np.nan
    return angle2rgb(stats.angle, nan_color=[0.5, 0.5, 0.5])


@contract(D='valid_diffeomorphism', returns='array[HxWx3](uint8)')
def diffeo_to_rgb_curv(D):
    stats = diffeo_stats(D)
    return posneg(stats.curv)


# TODO: add -pi, pi in contract
@contract(angle='array[HxW]', returns='array[HxWx3](uint8)')
def angle2rgb(angle, nan_color=[0, 0, 0]):
    H, W = angle.shape
    hsv = np.zeros((H, W, 3))
    for i, j in itertools.product(range(H), range(W)):
        hsv[i, j, 0] = (angle[i, j] + np.pi) / (2 * np.pi)
    hsv[:, :, 1] = 1
    hsv[:, :, 2] = 1

    isnan = np.isnan(angle)
    for k in range(3):
        hsv[:, :, k][isnan] = nan_color[k]

    try:
    # Try old interface
        from scikits.image.color import hsv2rgb  # @UnresolvedImport @UnusedImport
    except:
        # Try new interface
        from skimage.color import hsv2rgb  # @Reimport

    rgb = (hsv2rgb(hsv) * 255).astype('uint8')
    return rgb


@contract(shape='tuple(int,int)', returns='array[HxWx3](uint8)')
def angle_legend(shape, center=0):
    a = np.zeros(shape)
    H, W = shape
    for i, j in itertools.product(range(H), range(W)):
        x = i - H / 2.0
        y = j - W / 2.0
        r = np.hypot(x, y)
        if r <= center:
            a[i, j] = np.nan
        else:
            a[i, j] = np.arctan2(y, x)

    return angle2rgb(a)



@contract(D='valid_diffeomorphism')
def diffeo_to_rgb_inc(D):
    s = diffeo_stats(D)

    angle_int = ((s.angle + np.pi) * 255 / (np.pi * 2)).astype('int')
    if s.norm.max() > 0:
        norm = s.norm * 255 / s.norm.max()
    else:
        norm = s.norm
    M, N = D.shape[0], D.shape[1]
    rgb = np.zeros((M, N, 3), 'uint8')
    rgb[:, :, 0] = angle_int
    rgb[:, :, 1] = norm
    rgb[:, :, 2] = 1 - angle_int
    return rgb

