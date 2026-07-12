def classFactory(iface):
    from .computo_metrico_plugin import ComputoMetricoPlugin

    return ComputoMetricoPlugin(iface)
