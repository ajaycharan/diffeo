from diffeo2dds_learn import logger, DiffeoSystemEstimatorInterface
from contracts import contract
from diffeo2d_learn import Diffeo2dEstimatorInterface, get_diffeo2dlearn_config
from diffeo2dds import DiffeoAction, DiffeoSystem
import numpy as np
import warnings


__all__ = ['DiffeoSystemEstimator']


class DiffeoSystemEstimator(DiffeoSystemEstimatorInterface):
    
    '''
     
        Keeps a list of diffeomorphism estimators 
        to learn a diffeomorphism for each command.
        
        It can use different estimators for the diffeomorphism
        itself. These are specified using the id_diffeo_estimator
        parameter. 
    '''

    @contract(diffeo2d_estimator='str|code_spec')    
    def __init__(self, diffeo2d_estimator):
        '''

        '''
        self.command_list = []
        warnings.warn('TODO: remove state')
        self.state_list = []
        self.estimators = []
        self.estimators_inv = []
        
        self.diffeo2d_estimator = diffeo2d_estimator
        
        # becomes (i, n) if parallel_process_hint is called
        self.parallel_hint = None    
        
    def new_estimator(self):
        """ Instances a new estimator. """
        config = get_diffeo2dlearn_config()
        _, estimator = config.diffeo2d_estimators.instance_smarter(self.diffeo2d_estimator)
        return estimator            
                    
    @contract(returns='int', command='array')
    def command_index(self, command):
        command = tuple(command)
        # logger.info('Checking command %s in %r' % (str(command), self.command_list))
        # logger.info('%s' % str(command in self.command_list))
        
        if not command in self.command_list:    
            logger.info('Adding new command %s' % str(command))
            self.command_list.append(command)
            self.estimators.append(self.new_estimator())
            self.estimators_inv.append(self.new_estimator())
            
        index = self.command_list.index(command)
        return index 
         
    @contract(i='int,>=0,i', n='int,>=1,>=i')
    def parallel_process_hint(self, i, n):
        self.parallel_hint = (i, n)
        
    def merge(self, other):
        """ 
            Merges the values obtained by "other" with ours. 
            Note that we don't make a deep copy of structures.
        """
        for i in range(len(self.command_list)):
            # Note that they are not necessarily in the right order.
            command = self.command_list[i]
            if not command in other.command_list:
                logger.info('The other does not have %s' % str(command))
                logger.info('Ours: %s' % self.command_list)
                logger.info('His:  %s' % other.command_list)
                continue
            
            j = other.command_list.index(command)
            
            self.estimators[i].merge(other.estimators[j])
            self.estimators_inv[i].merge(other.estimators_inv[j])
            
        # Now add the ones we don't have.
        for j in range(len(other.command_list)):
            command = other.command_list[j]
            
            if len(other.state_list) <= j:
                state = 0
            else:
                state = other.state_list[j]
            
            if command in self.command_list:
                state_list = np.array(self.state_list)
                try:
                    if (state_list[self.command_list.index(command)] == state).all():
                        # Already have it
                        continue
                except:
                    pass
            logger.info('Adding command %s' % str(command))
            self.command_list.append(command)
            self.state_list.append(state)
            self.estimators.append(other.estimators[j])
            self.estimators_inv.append(other.estimators_inv[j])
        
    def update(self, y0, u0, y1, X0=None):
        cmd_ind = self.command_index(u0)
        
        if self.parallel_hint is not None:
            # check to see if we need to take care of this
            i, n = self.parallel_hint
            ours = cmd_ind % n == i
            if not ours:
                return
        
        est = self.estimators[cmd_ind]
        est_inv = self.estimators_inv[cmd_ind]
        # XXX: cleaning up with state or not
        if y0.ndim == 3:
            # if there are 3 channels...
            for ch in range(3):
                if X0 is None:
                    est.update(y0[:, :, ch], y1[:, :, ch])
                    est_inv.update(y1[:, :, ch], y0[:, :, ch])
                else:
                    est.update(y0[:, :, ch], y1[:, :, ch], u0, X0)
                    est_inv.update(y1[:, :, ch], y0[:, :, ch], u0, X0)
        else:
            assert y0.ndim == 2
            est.update(y0, y1)
            est_inv.update(y1, y0)
                
        
    @contract(returns=DiffeoSystem)            
    def get_value(self, prefix=''):
        n = len(self.estimators)
        action_list = []
        for i in range(n):
            command = np.array(self.command_list[i])
            name = prefix + str(list(command)).replace(' ', '')
            
            try:
                diffeo = self.estimators[i].get_value()
                diffeo_inv = self.estimators_inv[i].get_value()
            except Diffeo2dEstimatorInterface.NotReady:
                logger.info('Skipping command %r %r' % (i, command))
                continue
                
            name = 'Uninterpreted Diffeomorphism' + str(i)
            action = DiffeoAction(name, diffeo, diffeo_inv, command)
            
            warnings.warn('to put in a different place')
            # Use new update uncertainty method if param specifies so
            if hasattr(self, 'update_uncertainty') and self.update_uncertainty:
                action.update_uncertainty()
                
            action_list.append(action)
            
        name = 'Uninterpreted Diffeomorphism System'
        self.system = DiffeoSystem(name, action_list)
        return self.system
    
    def display(self, report): 
        for i in range(len(self.estimators)):
            logger.info('Report for %d-th action' % i)
            self.estimators[i].display(report.section('d%s' % i))
            self.estimators_inv[i].display(report.section('d%s-inv' % i))
            
            
# class DiffeoLearnerStatistics(DiffeoLearner):
#    def new_estimator(self):
#        return DiffeomorphismEstimatorFasterStatistics(**self.diffeo_estimator_params)

# class DiffeoLearnerRefine(DiffeoLearner):
#     def new_estimator(self):
#         return DiffeomorphismEstimatorRefine(**self.diffeo_estimator_params)
#     
#     def refine_init(self):
# #        pdb.set_trace()
#         for i in range(len(self.estimators)):
#             self.estimators[i].refine_init()
#         for i in range(len(self.estimators_inv)):
#             self.estimators_inv[i].refine_init()
#             
# class DiffeoLearnerRefineFast(DiffeoLearner):
#     def new_estimator(self):
#         return DiffeomorphismEstimatorRefineFast(**self.diffeo_estimator_params)
# 
#     def command_index(self, command):
#         if not command in self.command_list:    
#             logger.info('Adding new command %s' % str(command))
#             self.command_list.append(command)
#             estimator = self.new_estimator()
#             estimator_inv = self.new_estimator()
#             if hasattr(self, 'area_data'):
#                 estimator.set_search_areas(self.area_data[0][0], self.area_data[0][1])
#                 estimator_inv.set_search_areas(self.area_data[1][0], self.area_data[1][1])
#             self.estimators.append(estimator)
#             self.estimators_inv.append(estimator_inv)
#             
#         index = self.command_list.index(command)
#         return index
# 
#     def calculate_areas(self, dds, nrefine):
#         result = []
# #        pdb.set_trace()
#         logger.info('Calculating new areas, number of estimators are: %s' % len(self.estimators))
#         for i in range(len(self.estimators)):
#             diffeo = dds.actions[i].diffeo
#             diffeo_inv = dds.actions[i].diffeo_inv
#             res = self.estimators[i].calculate_areas(diffeo, nrefine)
#             res_inv = self.estimators[i].calculate_areas(diffeo_inv, nrefine)
#             result.append((res, res_inv))
#         return result
#     
#     def set_search_areas(self, area_data):
#         self.area_data = area_data
#     
# #    def refine_init(self):
# #        pdb.set_trace()
#        for i in range(len(self.estimators)):
#            self.estimators[i].refine_init()
#        for i in range(len(self.estimators_inv)):
#            self.estimators_inv[i].refine_init()
            
# class DiffeoLearnerPixelized(DiffeoLearner):
#    '''
#    This learner considers only specified pixels and has a completely different 
#    structure than all other learners. Not used in any paper by (March 2013)
#    '''
#        
#    def new_estimator(self):
#        return DiffeomorphismEstimatorPixelized(sensels=self.sensels,
#                                                **self.diffeo_estimator_params)
#    
#    def estimator_index(self, command, state=None):
#        if len(self.estimators) == 0:
#            self.estimators.append(self.new_estimator())
#            self.estimators_inv.append(self.new_estimator())
#        return 0
#    
#    def summarize(self):
#        action_list = []
#        
#        self.merge()
#        for i, cmd_state in enumerate(self.estimators[0].output_cmd_state):
#            command = cmd_state[:3]
#            state = cmd_state[3]
#            prefix = 'pix'
#            
#            name = prefix + str(list(command)).replace(' ', '')
#            diffeo = self.estimators[0].summarize(command, state)
#
#            diffeo_inv = self.estimators_inv[0].summarize(command, state)
#            name = 'Uninterpreted Diffeomorphism' + str(i)
#            action = DiffeoAction(name, diffeo, diffeo_inv, command, state)
#            action_list.append(action)
#        name = 'Pixelized Diffeomorphism System'
#        self.system = DiffeoSystem(name, action_list)
#        return self.system
#    
#    def merge(self):
#        for other in self.estimators[1:]:
#            self.estimators[0].merge(other)
#        for other in self.estimators_inv[1:]:
#            self.estimators_inv[0].merge(other)

# class DiffeoLearnerAnimation(DiffeoLearner):
#    '''
#    This learner was used to generate images for visualisation. The output may 
#    not be a working diffeomorphism.
#    '''
#    def new_estimator(self):    
#        if not hasattr(self, 'last_index'):
#            index = 0
#            logger.info('adding first estimator')
#        else:
#            index = self.last_index + 1
#            logger.info('adding new estimator')
#            
#        self.last_index = index
#        return DiffeomorphismEstimatorAnimation(index=index, **self.diffeo_estimator_params)
