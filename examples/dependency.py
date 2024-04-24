from dataclasses import dataclass

from kaiju_app import Service, service, ApplicationLoader, Configurator, run_app


class CacheService(Service):
    """A custom service."""

    def __init__(self, *args, host: str, port: int, **kws):
        super().__init__(*args, **kws)
        self.host = host
        self.port = port
        self._transport = None

    async def init(self):
        self._transport = 'NEW TRANSPORT'

    async def close(self):
        self._transport = None

    async def get(self, key: str):
        ...


@dataclass
class UserService(Service):
    cache: CacheService = service()

    async def get_user(self, user_id):
        return await self.cache.get(f'user:{user_id}')


example_config = {
    'packages': [],     # additional packages to import modules from
    'logging': {},      # logging settings, see `uvlog` documentation
    'app': {
        'name': 'app',
        'env': 'dev',
        'loglevel': 'DEBUG',
        'services': [
            {
                'cls': 'CacheService',
                'settings': {
                    'host': 'localhost',
                    'port': 8080
                }
            },
            {
                'cls': 'UserService',
            }
        ]
    }
}

example_env = {
    'cache_host': 'localhost',
    'cache_port': 6379
}


loader = ApplicationLoader(service_classes={'CacheService': CacheService})
configurator = Configurator()
config = configurator.create_configuration([example_config], [example_env])
app = loader.create_all(config)
run_app(app)
