import os

# Workaround for PyCharm's debugger which doesn't like this backport
# TODO: Remove this as soon as possible
if "PYDEVD_LOAD_VALUES_ASYNC" in os.environ:
    from unittest.mock import *  # noqa: F401
else:
    try:
        from mock import *
    except ImportError:
        from unittest.mock import *
