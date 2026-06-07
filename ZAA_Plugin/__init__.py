def getMetaData():
    return {}


def register(app):
    from . import ZAAExtension
    return {"extension": ZAAExtension.ZAAExtension()}
