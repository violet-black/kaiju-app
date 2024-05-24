.. _errors:

:tocdepth: 2

**errors** - error specification and codes
------------------------------------------

This file includes specification of common types of RPC compatible errors which are divided into certain logical groups.
The codes are made to be mostly compatible with the JSONRPC specification.

1. Use RPC error types only for those errors you'd like to expose to a client.
2. If you have to pass a Python exception, wrap it using `wrap_exception()` function.
3. Try to use the standard error types when possible.
4. Avoid formatted strings in messages. Pass additional values to error extras.

.. autoclass:: kaiju_app.errors.Error
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kaiju_app.errors.DataError
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kaiju_app.errors.PermissionError
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kaiju_app.errors.ServerError
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kaiju_app.errors.ClientError
   :members:
   :undoc-members:
   :show-inheritance:

.. data:: ERRORS

    A global mapping { error type id: error type }

.. autofunction:: kaiju_app.errors.create_error

.. autofunction:: kaiju_app.errors.wrap_exception
