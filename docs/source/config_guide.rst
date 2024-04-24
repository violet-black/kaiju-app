.. _config-guide:

Configuration guide
===================

Configurations are split into two types: one type is *template* and the other is *environment*. The idea is that you
have a template file structured in a certain way (see :ref:`config-spec`) with placeholders for actual values, and
the values themselves are provided using a flat-structured environment file.

.. note::

    The library doesn't impose any configuration file format by design. You may use any file formats compatible with
    config data. However the suggested options are to use JSON for environment files and either JSON or better YAML for
    structured templates. Or you can just use Python files.

When creating a configuration you pass a list of templates and a list of env dicts to the configurator.

.. code-block:: python

    config = configurator.create_configuration([template1, template2], [env1, env2])

The configurator does a few things there:

1. Merge all templates from first to last.
2. Merge all envs from first to last.
3. Add os environment variables on top of the resulting environment dictionary.
4. Add values from `--env` CLI flags on top of this.
5. Evaluate the template using  our `template-dict <http://template-dict.readthedocs.io>`_ library.
6. Normalize the resulting dictionary into a valid :py:class:`kaiju_app.loader.ProjectConfig` dict.

To illustrate this, imagine you have a config file like this:

.. code-block:: yaml
  :caption: settings/config.yaml

    debug: False
    app:
        name: app
        env: "[env]"
        loglevel: "[loglevel:'DEBUG']
        services:
            cls: DatabaseService
            settings:
                db_host: "[db_host]"
                db_port: "[db_port]"

The values in square brackets are placeholders - they will be evaluated once an environment dictionary is provided.

.. code-block:: json
  :caption: settings/env.json

    {
        "env": "local"
        "db_host": "0.0.0.0",
        "db_port": 5432
    }

Note that you may specify default values using `template-dict <http://template-dict.readthedocs.io>`_ synthax for
defaults, like this: `"[loglevel:'DEBUG']`. The value after ':' is evaluated safely to a Python simple type.

Suppose you provided the both files to your configurator but you also specified a couple of system variables.

.. code-block:: console

    export env='prod'
    export debug=True

In the example above the second variable (debug) will be ignored since it doesn't have a placeholder. The first
variable (env) will be loaded and evaluated replacing the value from the env file.

.. note::

    Try to remember that env and CLI values are evaluated to Python types. Passing `env=42` would result in an integer
    value. To prevent this use braces: `env='42'`
