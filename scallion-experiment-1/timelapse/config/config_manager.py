from .log_config import LogConfig


def get_config_base(cls, name):
    if name not in cls.instances:
        cls.instances[name] = cls.configs[name]()
    return cls.instances[name]

class ConfigManager:
    configs = dict(
        log_config=LogConfig,
    )
    instances = {}


    def __init__(self):
        raise Exception("{} is class only".format(self.__class__.__name__))

    @classmethod
    def init_configs(cls):
        for name, config_cls in cls.configs.items():
            cls.instances[name] = config_cls()
            instance = cls.instances[name]
            setattr(cls, "get_" + name, classmethod(lambda c, instance=instance: instance))


ConfigManager.init_configs()
