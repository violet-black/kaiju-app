[![pypi](https://img.shields.io/pypi/v/kaiju-app.svg)](https://pypi.python.org/pypi/kaiju-app/)
[![docs](https://readthedocs.org/projects/kaiju-app/badge/?version=latest&style=flat)](https://kaiju-app.readthedocs.io)
[![codecov](https://codecov.io/gh/violet-black/kaiju-app/graph/badge.svg?token=FEUUMQELFX)](https://codecov.io/gh/violet-black/kaiju-app)
[![tests](https://github.com/violet-black/kaiju-app/actions/workflows/tests.yaml/badge.svg)](https://github.com/violet-black/kaiju-app/actions/workflows/tests.yaml)
[![mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[![python](https://img.shields.io/pypi/pyversions/kaiju-app.svg)](https://pypi.python.org/pypi/kaiju-app/)

**kaiju-app** - application and service base classes. They can be used as
building blocks for various asyncio server applications. The library provides base classes, configuration loader and
application builder and service dependency resolution mechanisms.

# Installation

With pip and python 3.12+:

```bash
pip3 install kaiju-app
```

# How to use

See the [user guide](https://kaiju-app.readthedocs.io/guide.html) for more info.

Create a service with custom methods, initialization and de-initialization.

```python
from kaiju_app import Service

class CacheService(Service):

    def __init__(self, host: str, port: int, password: str):
        ...

    async def init(self):
        self._transport = await self._initialize_transport()

    async def close(self):
        self._transport.close()

    async def load_cache(self):
        ...

```

Create a loader and register your service class there.

```python
from kaiju_app import ApplicationLoader

loader = ApplicationLoader()
loader.service_classes['CacheService'] = CacheService
```

Load your configuration using a configurator and create an application with your services in it. You may use JSON
or YAML file loader here instead of implementing the whole config in Python.

```python
from kaiju_app import Configurator, ProjectConfig, AppConfig, ServiceConfig

example_config = ProjectConfig(
    packages=[],
    logging={},
    app=AppConfig(
        name='my_app',
        env='dev',
        services=[
            ServiceConfig(
                cls='CacheService',
                settings={
                    'host': '[cache_host]',
                    'port': '[cache_port]',
                    'password': '[cache_password]'
                }
            )
        ]
    )
)

example_env = {
    'cache_host': 'localhost',
    'cache_port': 6379,
    'cache_password': 'qwerty'
}

configurator = Configurator()
config = configurator.create_configuration([example_config], [example_env])
```

The idea behind configuration is that it split on two types of files: config (template) files and env files. Config
files are structured and must obey `ProjectConfig` special config format. Env files are flat and used to copy values
from, so env file may be a simple plain JSON or a text file or a set of environment variables. You can use any number
of template files and env files in your config - they will be merged.

The configurator uses [template-dict](http://template-dict.readthedocs.io) to fill the templates.

Next you can pass the resulting config to the `AppLoader` and create an application which can be run in an asyncio loop.
The `run_app` function allows you to run the app forever in an asyncio loop until a `ctrl+C` signal is received.

```python
from kaiju_app import run_app

app = loader.create_all(config)
run_app(app)
```
