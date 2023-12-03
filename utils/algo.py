from typing import Iterable


def remove_duplicates_keep_order(iterable: Iterable):
    """
    Remove duplicates from an iterable while keeping order. Returns a list.
    """
    return list(dict.fromkeys(iterable))
