import asyncio


def remove_tornado_fix() -> None:
    """
    UNDOES THE FOLLOWING OBSOLETE FIX IN streamlit.web.bootstrap.run():
    Set default asyncio policy to be compatible with Tornado 6.

    Tornado 6 (at least) is not compatible with the default
    asyncio implementation on Windows. So here we
    pick the older SelectorEventLoopPolicy when the OS is Windows
    if the known-incompatible default policy is in use.

    This has to happen as early as possible to make it a low priority and
    overridable

    See: https://github.com/tornadoweb/tornado/issues/2608

    FIXME: if/when tornado supports the defaults in asyncio,
    remove and bump tornado requirement for py38
    """
    try:
        from asyncio import (  # type: ignore[attr-defined]
            WindowsProactorEventLoopPolicy,
            WindowsSelectorEventLoopPolicy,
        )
    except ImportError:
        pass
        # Not affected
    else:
        if type(asyncio.get_event_loop_policy()) is WindowsSelectorEventLoopPolicy:
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
