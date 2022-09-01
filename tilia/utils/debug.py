# TODO where should i put these?


def create_tracked_obj(alias: str, cls: type, *args, **kwargs):
    class TrackedObject(cls):
        def __init__(self):
            self.alias = alias
            cls.__init__(self, *args, **kwargs)

        def __getattribute__(self, name):
            attr = object.__getattribute__(self, name)
            if hasattr(attr, "__call__"):

                def tracked_getattribute(*args, **kwargs):
                    print(f"Calling {attr.__name__} on {self.alias}, call stack below:")
                    pprint_call_stack(1, -3)
                    print("--------")
                    result = attr(*args, **kwargs)
                    return result

                return tracked_getattribute
            else:
                return attr

    return TrackedObject()


def pprint_call_stack(start_index: int, end_index: int):
    import pprint

    pprint.pprint(get_call_stack()[start_index, end_index])


def get_call_stack():
    import inspect
    from os import path

    curframe = inspect.currentframe()
    calframe = inspect.getouterframes(curframe, 2)
    relevant_info = [(path.basename(cf[1]), cf[2], cf[3]) for cf in calframe[2:]]
    return relevant_info
