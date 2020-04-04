import importlib
import logging
import pkgutil

import exchangelib


def _import_submodules(package, recursive=True):
    """ Import all submodules of a module, recursively, including subpackages
    :param package: package (name or actual module)
    :type package: str | module
    :rtype: dict[str, types.ModuleType]
    https://stackoverflow.com/questions/3365740/how-to-import-all-submodules
    """
    if isinstance(package, str):
        package = importlib.import_module(package)
    results = {}
    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + '.' + name
        results[full_name] = importlib.import_module(full_name)
        if recursive and is_pkg:
            results.update(_import_submodules(full_name))
    return results

__LOGGERS = None

@property
def loggers():
    """Return exchangelib loggers, lazily evaluated"""
    if __LOGGERS is None:
        __LIB_LOGGERS = []

        results = _import_submodules(exchangelib)
        for r in results:
            try:
                lg = eval("{}.log".format(r))
                if isinstance(lg,logging.Logger):
                    __LOGGERS.append(lg)
            except AttributeError:
                pass
    return __LOGGERS

def setLevel(level:int)->None:
    """Set logging for all modules in exchangelib"""
    for logger in loggers:
        logger.setLevel(level)