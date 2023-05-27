class TimelineUIElement:
    def __init__(self, component, **kwargs):
        self.component = component

    @classmethod
    def create(cls, component, **kwargs):
        return cls(component, **kwargs)
