from typing import Iterable, Iterator, Any
from itertools import zip_longest


def interleave_iterables(iterables: Iterable[Iterable[Any]]) -> Iterator[Any]:
    """
    Interleave elements from multiple iterables.

    This function takes an iterable of iterables (like lists, tuples, etc.) and yields elements
    in an interleaved manner: first yielding the first element of each iterable, then the second
    element of each, and so on. If an iterable is exhausted (shorter than others), it is skipped.

    Example:
    >>> list(interleave_iterables([[1, 2, 3], ('a', 'b'), [10, 20, 30, 40]]))
    [1, 'a', 10, 2, 'b', 20, 3, 30, 40]
    """

    sentinel = object()  # unique object to identify exhausted sublists

    for elements in zip_longest(*iterables, fillvalue=sentinel):
        for element in elements:
            if element is not sentinel:
                yield element


def remove_duplicates_keep_order(iterable: Iterable):
    """
    Remove duplicates from an iterable while keeping order. Returns a list.
    """
    return list(dict.fromkeys(iterable))
