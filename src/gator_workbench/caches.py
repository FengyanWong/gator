"""Every cache a workbench process keeps for its lifetime, by name (refactoring package B10). Each cache keeps its own
key recipe and its own variable - tests empty several of them by that name - and registers here how it is emptied, so
that one call empties them all and one list names them all (tests/workbench/test_wb_caches.py holds every new one to it).

Not caches, so not here: the locks a start hands to its worker (runs._HELD_LOCKS, corner_check._STARTING), the open
OCEAN clients (ocean._CLIENTS: emptying the dict would leave them open), Save task's timing record
(task_saving._took) and paths.repo_root, which never changes."""
from __future__ import annotations

_CLEARS: dict = {}


def register(module_globals, name, *, lock=None) -> str:
    """Join the registry: `name` is a cache the module whose globals these are holds as a global - a dict (an OrderedDict
    too), emptied by .clear(), or a function under functools.lru_cache, emptied by .cache_clear(). It is looked up when
    it is emptied, so a test that swaps it for another object is followed; `lock` names the module's global lock that
    is held around the cache. Returns the cache's name in the registry: '<module>.<name>'."""
    key = f"{module_globals['__name__'].removeprefix('gator_workbench.')}.{name}"

    def clear():
        cache = module_globals[name]
        empty = cache.cache_clear if hasattr(cache, 'cache_clear') else cache.clear
        if lock is None:
            empty()
        else:
            with module_globals[lock]:
                empty()
    _CLEARS[key] = clear
    return key


def names() -> list:
    return sorted(_CLEARS)


def clear_all() -> None:
    """Empty every registered cache: a test that wants a cold process, or a process that must read every file again."""
    for clear in list(_CLEARS.values()):
        clear()
