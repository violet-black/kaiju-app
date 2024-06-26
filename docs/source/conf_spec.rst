.. _config-spec:

Configuration specification
===========================

A complete config file would look like the following.

.. code-block:: yaml

    debug: ...
    packages: ...
    logging: ...
    app: ...

The sections of the file are described below. Yaml format is used for convenience.

debug
-----

: bool = False

Run the whole project in debug mode.

packages
--------

Packages section may contain a list of service packages names to import service classes from.
See :ref:`packages-guide` on how to create service packages.

.. code-block:: yaml

    packages:
        - "my_pkg1"
        - "my_pkg2"

logging
-------

In `logging` section you may provide loggers and handles configuration options. By default the app uses
`uvlog configure <https://uvlog.readthedocs.io/reference.html#uvlog.configure>`_ to configure a new logger. See the
official documentation for detail.

.. code-block:: yaml

    logging:
        loggers:
            my_app:
                handlers: ["stderr"]
        handlers:
            stderr:
                cls: "QueueStreamHandler"
                formatter: "json"
        formatters:
            json:
                keys: ["message", "name", "asctime", "ctx", "extra"]

loggers
^^^^^^^

List of pre-initialized loggers and their settings. You can customize application logger settings here by using
the app name for the logger name (key). All service loggers are also derived from the app logger when an app
is created.

**handlers**

: list[str] = ['stderr']

Customize the list of handlers for this particular logger and its children.

handlers
^^^^^^^^

You can customize handlers behaviour in this sections. The default customizable handlers are: `stderr` and `stdout`.

**cls**

: str

Handler type for this handler. It's `StreamHandler` by default.

**formatter**

: str = 'text'

Formatter used for this particular handler. It's `text` by default.

formatters
^^^^^^^^^^

You can customize log formatters in this section. The default two types of formatters are `json` and `text`.

**keys**

: str

For `json` formatter only: list of keys in a log message to serialize. By default all keys are serialized.

app
---

This is the application section of the config. It contains the application settings as well as all described services
and their configurations.

.. code-block:: yaml

    app:
        name: "my_app"
        env: "prod"
        loglevel: "INFO"
        scheduler:
        server:
            max_parallel_tasks: 256
        settings:
            service_start_timeout_s: 60
            some_setting: "abc"
        optional_services:
            - "EchoService"
        services:
            - cls: "EchoService"
              name: "echo"
              enabled: True
              loglevel: "ERROR"
              settings:
                some_setting: "abc"

name
^^^^

: str (required)

Application name. The name should be unique for each application. Applications may use the name as a prefix for cache
keys, queues, database names, etc.

env
^^^

: str (required)

Application environment name. Generally you should stick to a few specific environments like *qa*, *prod*, *dev*
*test* and use them exclusively. Applications may use the env name as a prefix for cache keys, queues, database names, etc.

loglevel
^^^^^^^^

: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "EXCEPTION"

Override log level for the application logger. Since all services are initialized from the application logger as a parent
this also sets the log level for all the service loggers.

scheduler
^^^^^^^^^

Application internal task scheduler settings. Currently nothing of interest to store here. This value can be omitted.
See :py:class:`~kaiju_app.scheduler.Scheduler` for more info.

server
^^^^^^

Application internal task server settings available via `app.server`.
See :py:class:`~kaiju_app.scheduler.Server` for more info.

**max_parallel_tasks**

: int = 256

Maximum number of concurrent tasks submitted to the asyncio loop.

settings
^^^^^^^^

Application parameters are passed directly to the `Application.__init__()` on creating an app. You can write any
arbitrary parameters there as long as they are present in the init section.

A few notable settings for the base application:

**service_start_timeout_s**

: float = 30

Maximum allowed time in seconds for each service to start.

**post_init_timeout_s**

: float = 300

Maximum allowed time in seconds for each service to execute its `post_init` method.

**max_parallel_tasks**

: int = 128

Max parallel asyncio tasks submitted to the internal server simultaneously.

**show_inspection_on_start**

: bool

Output inspection data to the logs after the app start.

**metadata**

: dict

Arbitrary metadata. Should not be used by anything but logs / inspections.

optional_services
^^^^^^^^^^^^^^^^^

: list[str]

List of optional services (not required to start).

services
^^^^^^^^

: list

A list of service configurations for this application. On creating an app services are created from top to bottom,
however they are started in order of their dependency resolution.

**cls**

: str

Service class name. The class must be registered in the application loader `service_classes` dict.

**name**

: str

Service custom name. By default equals to the class name.

**enabled**

: bool = True

Service is enabled. Set it to false to completely skip the service.

**loglevel**

: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "EXCEPTION"

Override service logger level for this particular service.

**settings**

Arbitrary settings for the service `__init__()`. You can use any prameters in there as long as they present in the
service init.
