from conf_tools.utils import check_is_in
from contracts import contract
from diffeo2d import Diffeomorphism2D, Flattening, coords_iterate, cmap
from diffeo2d_learn import Diffeo2dEstimatorInterface, logger
import numpy as np

__all__ = ['DiffeomorphismEstimatorSimple']


class DiffeomorphismEstimatorSimple(Diffeo2dEstimatorInterface):
    ''' 
        Learns a discretized diffeomorphism between two 2D images. 
        
    '''

    @contract(match_method='str')
    def __init__(self, match_method):
        """ 
            :param max_displ: Maximum pointwise displacement for the diffeomorphism d_max
            :param match_method: Either "continuous" or "binary" (to compute the 
                error function).
        """
        self.shape = None
        self.last_y0 = None
        self.last_y1 = None

        accepted = [MATCH_CONTINUOUS, MATCH_BINARY]
        check_is_in('match method', match_method, accepted)
        self.match_method = match_method

        self.num_samples = 0

    def set_max_displ(self, max_displ):
        self.max_displ = np.array(max_displ)
   
    @contract(returns='bool')
    def initialized(self):
        return self.shape is not None

    @contract(y0='array[MxN]', y1='array[MxN]')
    def update(self, y0, y1):
        self.num_samples += 1

        # init structures if not already
        if self.shape is None:
            self.init_structures(y0.shape)

        # check shape didn't change
        if self.shape != y0.shape:
            msg = 'Shape changed from %s to %s.' % (self.shape, y0.shape)
            raise ValueError(msg)

        # remember last images
        self.last_y0 = y0
        self.last_y1 = y1

        # Chooses the error function based on the parameter in contructor
        if self.match_method == MATCH_CONTINUOUS:
            similarity = sim_continuous
        elif self.match_method == MATCH_BINARY:
            similarity = sim_binary
        else:
            assert False

        # "Converts" the images to one dimensional vectors
        y0_flat = y0.flat
        y1_flat = y1.flat
        # For each pixel in the second image
        for k in range(self.nsensels):
            # Look at its value "a"
            a = y1_flat[k]
            # Look which originally was closer
            # these values: self.neighbor_indices_flat[k] 
            # give you which indices in the flat vectors are 
            # close to k-th pixel
            
            # values of the neighbors 
            b = y0_flat[self.neighbor_indices_flat[k]]
            
            # compute similarity
            neighbor_sim = similarity(a, b)
            
            # compute the similarity order
            neighbor_argsort = np.zeros(len(neighbor_sim))
            neighbor_argsort[np.argsort(neighbor_sim)] += range(len(neighbor_sim))
            
            # compute best similarity
            self.neighbor_num_bestmatch_flat[k] += (neighbor_sim != np.min(neighbor_sim))  
            
            # keep track of which neighbors are more similar on average
            self.neighbor_similarity_flat[k] += neighbor_sim
            self.neighbor_similarity_best[k] += np.min(neighbor_sim)
            self.neighbor_argsort_flat[k] += neighbor_argsort

    def merge(self, other):
        
        if not other.initialized():
            return
        
        if not self.initialized() and other.initialized():
            self.init_structures(other.shape)
            self.num_samples = other.num_samples
            self.neighbor_similarity_flat = other.neighbor_similarity_flat
            self.neighbor_similarity_best = other.neighbor_similarity_best
            self.neighbor_argsort_flat = other.neighbor_argsort_flat            
            return
        
        assert self.initialized() and other.initialized()
        self.num_samples += other.num_samples
        self.neighbor_similarity_flat += other.neighbor_similarity_flat
        self.neighbor_similarity_best += other.neighbor_similarity_best
        self.neighbor_argsort_flat += other.neighbor_argsort_flat

    @contract(shape='seq[2](int, >0)')
    def init_structures(self, shape):
        self.shape = shape
        self.nsensels = shape[0] * shape[1]

        self.ydd = np.zeros(shape, dtype='float32')

        # for each sensel, create an area
        self.lengths = np.ceil(self.max_displ * 
                               np.array(self.shape)).astype('int32')
        # print(' Field Shape: %s' % str(self.shape))
        # print('    Fraction: %s' % str(self.max_displ))
        # print(' Search area: %s' % str(self.lengths))

        self.neighbor_coords = [None] * self.nsensels
        self.neighbor_indices = [None] * self.nsensels
        self.neighbor_indices_flat = [None] * self.nsensels
        self.neighbor_similarity_flat = [None] * self.nsensels
        self.neighbor_similarity_best = np.zeros(self.nsensels, dtype='float32')
        self.neighbor_argsort_flat = [None] * self.nsensels
        self.neighbor_num_bestmatch_flat = [None] * self.nsensels

        self.flattening = Flattening.by_rows(shape)
        logger.info('Creating structure shape %s lengths %s' % 
                  (self.shape, self.lengths))
        cmg = cmap(self.lengths)
        for coord in coords_iterate(self.shape):
            k = self.flattening.cell2index[coord]
            cm = cmg.copy()
            cm[:, :, 0] += coord[0]
            cm[:, :, 1] += coord[1]
            cm[:, :, 0] = cm[:, :, 0] % self.shape[0]
            cm[:, :, 1] = cm[:, :, 1] % self.shape[1]
            self.neighbor_coords[k] = cm

            indices = np.zeros(self.lengths, 'int32')
            for a, b in coords_iterate(indices.shape):
                c = tuple(cm[a, b, :])
                indices[a, b] = self.flattening.cell2index[c]

            self.neighbor_indices[k] = indices
            self.neighbor_indices_flat[k] = np.array(indices.flat)
            self.neighbor_similarity_flat[k] = np.zeros(indices.size, 'float32')
            self.neighbor_argsort_flat[k] = np.zeros(indices.size, 'float32')
            self.neighbor_num_bestmatch_flat[k] = np.zeros(indices.size, 'uint')
        
    
    def get_value(self):
        ''' 
            Find maximum likelihood estimate for diffeomorphism looking 
            at each pixel singularly. 
            
            Returns a Diffeomorphism2D.
        '''
        
        if not self.initialized():
            msg = 'No data seen yet'
            raise Diffeo2dEstimatorInterface.NotReady(msg)
        
        maximum_likelihood_index = np.zeros(self.shape, dtype='int32')
        variance = np.zeros(self.shape, dtype='float32')
        E2 = np.zeros(self.shape, dtype='float32')
        E3 = np.zeros(self.shape, dtype='float32')
        E4 = np.zeros(self.shape, dtype='float32')
        num_problems = 0
        

        i = 0
        # for each coordinate
        for c in coords_iterate(self.shape):
            # find index in flat array
            k = self.flattening.cell2index[c]
            # Look at the average similarities of the neihgbors
            sim = self.neighbor_similarity_flat[k]
            sim_min = sim.min()
            sim_max = sim.max()
            if sim_max == sim_min:
                # if all the neighbors have the same similarity
                best_index = 0
                variance[c] = 0  # minimum information
                maximum_likelihood_index[c] = best_index
            else:
                best = np.argmin(sim)
                best_index = self.neighbor_indices_flat[k][best]
                # uncertainty ~= similarity of the best pixel
                variance[c] = sim[best]   
                maximum_likelihood_index[c] = best_index
            
        
            E2[c] = self.neighbor_similarity_best[k] / self.num_samples
            # Best match error
            E3[c] = np.min(self.neighbor_num_bestmatch_flat[k]) / self.num_samples
            
            E4[c] = np.min(self.neighbor_argsort_flat[k]) / self.num_samples
            
            i += 1
        
        d = self.flattening.flat2coords(maximum_likelihood_index)

        if num_problems > 0:
            logger.info('Warning, %d were not informative.' % num_problems)
            pass
        
        # normalization for this variance measure
        vmin = variance.min()
        variance = variance - vmin
        vmax = variance.max()
        if vmax > 0:
            variance *= (1 / vmax)
            
        # return maximum likelihood plus uncertainty measure
        return Diffeomorphism2D(d, variance)  # , E2, E3, E4)
    
    def summarize_continuous(self, quivername):
        center = np.zeros(list(self.shape) + [2], dtype='float32')
        spread = np.zeros(self.shape, dtype='float32')
        maxerror = np.zeros(self.shape, dtype='float32')
        minerror = np.zeros(self.shape, dtype='float32')
        
        # from PIL import Image  # @UnresolvedImport
        # sim_image = Image.new('L', np.flipud(self.shape) * np.flipud(self.lengths))
        # zer_image = Image.new('L', np.flipud(self.shape) * np.flipud(self.lengths))
        for c in coords_iterate(self.shape):
            # find index in flat array
            k = self.flattening.cell2index[c]
            # Look at the average similarities of the neihgbors
            sim = self.neighbor_similarity_flat[k]
            
            sim_square = sim.reshape(self.lengths).astype('float32') / self.num_samples
            from diffeo2d_learn.library.simple.display import sim_square_modify
            sim_square, minerror[c], maxerror[c] = sim_square_modify(sim_square, np.min(self.neighbor_similarity_flat) / self.num_samples, np.max(self.neighbor_similarity_flat) / self.num_samples)
            # avg_square = (np.max(sim_square) + np.min(sim_square)) / 2
            sim_zeroed = np.zeros(sim_square.shape)
            sim_zeroed[sim_square > 0.85] = sim_square[sim_square > 0.85] 
            from diffeo2d_learn.library.simple.display import get_cm
            center[c], spread[c] = get_cm(sim_square)

            # p0 = tuple(np.flipud(np.array(c) * self.lengths))
            # sim_image.paste(Image.fromarray((sim_square * 255).astype('uint8')), p0 + tuple(p0 + self.lengths))
            # zer_image.paste(Image.fromarray((sim_zeroed * 255).astype('uint8')), p0 + tuple(p0 + self.lengths))
            
        # sim_image.save(quivername + 'simimage.png')
        # zer_image.save(quivername + 'simzeroed.png')
            
            
        from diffeo2d_learn.library.simple.display import display_disp_quiver
        display_disp_quiver(center, quivername)
        from diffeo2d_learn.library.simple.display import display_continuous_stats
        display_continuous_stats(center, spread, minerror, maxerror, quivername)
        
        dcont = displacement_to_coord(center)
        diff = dcont.astype('int')
        diff = get_valid_diffeomorphism(diff)
        diffeo2d = Diffeomorphism2D(diff)
        
        return diffeo2d
        
    def summarize_smooth(self, noise=0.1):
        ''' Find best estimate for diffeomorphism 
            looking at each singularly. '''
        maximum_likelihood_index = np.zeros(self.shape, dtype='int32')
        variance = np.zeros(self.shape, dtype='float32')
        epsilon = None
        for c in coords_iterate(self.shape):
            k = self.flattening.cell2index[c]
            sim = self.neighbor_similarity_flat[k]
            if epsilon is None:
                epsilon = np.random.randn(*sim.shape)
            sim_min = sim.min()
            sim_max = sim.max()
            if sim_max == sim_min:
                best_index = 0
                variance[c] = 0
            else:
                std = noise * (sim_max - sim_min)
                best = np.argmin(sim + epsilon * std)
                best_index = self.neighbor_indices_flat[k][best]
                variance[c] = sim[best]
            maximum_likelihood_index[c] = best_index
        d = self.flattening.flat2coords(maximum_likelihood_index)
        variance = variance - variance.min()
        vmax = variance.max()
        if vmax > 0:
            variance *= (1 / vmax)
        return Diffeomorphism2D(d, variance)

    #    @contract(coords='tuple(int,int)') # XXX: int32 not accepted
    def get_similarity(self, coords):
        ''' Returns the similarity field for one cell. (outside are NaN) '''
        k = self.flattening.cell2index[coords]
        M = np.zeros(self.shape)
        M.fill(np.nan)
        neighbors = self.neighbor_indices_flat[k]
        sim = self.neighbor_similarity_flat[k]
        M.flat[neighbors] = sim
        best = np.argmax(sim)
        M.flat[neighbors[best]] = np.NaN
        return M

    def summarize_averaged(self, n=10, noise=0.1):
        d = []
        for _ in range(n):
            diff = self.summarize_smooth(noise)
            d.append(diff.d)
            # print('.')
        ds = np.array(d, 'float')
        avg = ds.mean(axis=0)
        # var  = diff.variance
        var = ds[:, :, :, 0].var(axis=0) + ds[:, :, :, 1].var(axis=0)
        # print var.shape
        assert avg.shape == diff.d.shape
        return Diffeomorphism2D(avg, var)

    def display(self, report):
        if not self.initialized():
            report.text('warn', 'not initialized')
            return
            
        f = report.figure('estimated')

        report.data('num_samples', self.num_samples)
        
        if self.num_samples == 0:
            return

        n = 20
        M = None
        for i in range(n):  # @UnusedVariable
            c = self.flattening.random_coords()
            Mc = self.get_similarity(c)
            if M is None:
                M = np.zeros(Mc.shape)
                M.fill(np.nan)

            ok = np.isfinite(Mc)
            Mmax = np.nanmax(Mc)
            if Mmax < 0:
                Mc = -Mc
                Mmax = -Mmax
            if Mmax > 0:
                M[ok] = Mc[ok] / Mmax

        report.data('coords', M).display('scale').add_to(f)

        if self.last_y0 is not None:
            f2 = report.figure('last_input')
            y0 = self.last_y0
            y1 = self.last_y1
            none = np.logical_and(y0 == 0, y1 == 0)
            x = y0 - y1
            x[none] = np.nan
            report.data('y0', y0).display('scale').add_to(f2, caption='y0')
            report.data('y1', y1).display('scale').add_to(f2, caption='y1')
            report.data('motion', x).display('posneg').add_to(f2, caption='motion')


def sim_continuous(a, b):
    a = a.astype('float32')
    b = b.astype('float32')
#     diff = np.abs(a.astype(np.int16) - b.astype(np.int16)) ** 2
    diff = np.abs(a - b) ** 2
    return diff

def sim_binary(a, b):  # good for data in 0-1
    return a * b


MATCH_CONTINUOUS = 'continuous'
MATCH_BINARY = 'binary'




# ## Test functions
# TODO: remove
@contract(x='array[MxNx2]')
def get_valid_diffeomorphism(x):
    M, N = x.shape[0], x.shape[1]
    
    # assert (0 <= x[:, :, 0]).all()
    # assert (0 <= x[:, :, 1]).all()
    x[x < 0] = 0
    
    # assert (x[:, :, 0] < M).all()
    x[x[:, :, 0] >= M] = M - 1
    
    # assert (x[:, :, 1] < N).all()
    x[x[:, :, 1] >= N] = N - 1
    
    return x
    
@contract(x='array[MxNx2]')
def displacement_to_coord(x):
    Y, X = np.meshgrid(range(x.shape[1]), range(x.shape[0]))
    
    x[:, :, 0] = x[:, :, 0] + Y
    x[:, :, 1] = x[:, :, 1] + X
    
    return x


