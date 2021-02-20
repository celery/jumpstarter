import typing


def fully_qualified_name(obj: typing.Any) -> str:
    return f"{obj.__module__}.{obj.__qualname__}"
