import typing


class persistent(property):
    def __init__(self):
        super().__init__(fget=self.get, fset=self.set, fdel=self.delete)

    def get(self, obj: typing.Any) -> typing.Any:
        actor_id = obj.actor_id
        cache = obj.cache

        return cache[f"{self.namespace}:{actor_id}"]

    def set(self, obj: typing.Any, value: typing.Any) -> typing.Any:
        actor_id = obj.actor_id
        cache = obj.cache

        cache[f"{self.namespace}:{actor_id}"] = value

    def delete(self, obj):
        actor_id = obj.actor_id
        cache = obj.cache

        del cache[f"{self.namespace}:{actor_id}"]

    def __set_name__(self, owner, name):
        self.namespace = f"{owner.__qualname__}:{name}"