from kaiju_app import Service, ApplicationLoader, Configurator, run_app, Application


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

    async def load_cache(self):
        ...


example_config = {
    'debug': True,
    'packages': [],     # additional packages to import modules from
    'logging': {
        'formatters': {
            'text': {
                'format': '{asctime} | {message} | {extra}'
            }
        }
    },      # logging settings, see `uvlog` documentation
    'app': {
        'name': 'app',
        'env': 'dev',
        'loglevel': 'INFO',
        'services': [
            {
                'cls': 'CacheService',
                'settings': {
                    'host': 'localhost',
                    'port': 8080
                }
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
app = loader.create_all(Application, config)
run_app(app)
