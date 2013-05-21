from bootstrapping_olympics import (AgentInterface, UnsupportedSpec,
    get_boot_config)
from contracts import contract
from diffeo2dds_learn import get_diffeo2ddslearn_config


__all__ = ['Diffeo2Agent']

class Diffeo2Agent(AgentInterface):
    '''
    
    '''
    
    @contract(explorer='string|code_spec',
              estimator='string|code_spec')
    def __init__(self, explorer, estimator, servo): 
        '''
        
        :param explorer: Explorer agent
        :param estimator: resolves to a DiffeoSystemEstimatorInterface
        :param servo: todo
        '''
        self.explorer_spec = explorer
        self.estimator_spec = estimator
        self.servo_spec = servo
        
        self.last_obs = None
        self.last_data = None
        
    def init(self, boot_spec):
        if len(boot_spec.get_observations().shape()) != 2:
            msg = 'This agent can only work with 2D signals.'
            raise UnsupportedSpec(msg)

        estimators = get_diffeo2ddslearn_config().diffeosystem_estimators 
        _, self.diffeosystem_estimator = estimators.instance_smarter(self.estimator_spec)
        
        # initialize explorer
        agents = get_boot_config().agents
        _, self.explorer = agents.instance_smarter(self.explorer_spec)
        self.explorer.init(boot_spec)
        
    def process_observations(self, obs):
        if self.last_obs is not None:
            t0 = self.last_obs['timestamp']
            t1 = obs['timestamp']
            delta = t1 - t0
            u = obs['commands']
            y0 = self.last_obs['observations']
            y1 = obs['observations']
            
            self.last_data = (y0, u, y1)
            self.info('t0: %.3f t1: %.3f delta: %.3f u: %s' % (t0, t1, delta, u))
            self.diffeosystem_estimator.update(y0=y0, u0=u, y1=y1)
        self.last_obs = obs
        
    def choose_commands(self):
        return self.explorer.choose_commands()

    def merge(self, other):
        self.diffeosystem_estimator.merge(other.diffeosystem_estimator)
        return self

    def display(self, report):
        with report.subsection('estimator') as sub:
            self.diffeosystem_estimator.display(sub)
        with report.subsection('model') as sub:
            discdds = self.diffeosystem_estimator.get_value()
            discdds.display(sub)
    
    def publish(self, pub):
        return self.display(pub.r)  # XXX
    
    
# 
#         if self.last_data is not None:
#             y0, u, y1 = self.last_data
#             none = np.logical_and(y0 == 0, y1 == 0)
#             x = y0 - y1
#             x[none] = np.nan
# 
#             pub.array_as_image('y0', y0, filter='scale')
#             pub.array_as_image('y1', y1, filter='scale')
#             pub.array_as_image('motion', x, filter='posneg')
# 
# #         if self.diffeo_dynamics.commands2dynamics:  # at least one
# #             de = self.diffeo_dynamics.commands2dynamics[0]
# #             field = de.get_similarity((10, 10))
# #             pub.array_as_image('field', field)
# 
#         self.diffeosystem_estimator.publish(pub.section('commands'))


