import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


from .configuration import *
from .interfaces import *
from .symdiffeo import *
from . import library



def get_comptests():
    from . import unittests
    from comptests import get_comptests_app
    app = get_comptests_app(get_diffeo2s_config())
    return [app]
