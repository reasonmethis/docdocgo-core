from itertools import zip_longest
from typing import Any, Iterable, Iterator


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


def insert_interval(
    current_intervals: list[tuple[int, int]], new_interval: tuple[int, int]
) -> list[tuple[int, int]]:
    """
    Add a new interval to a list of sorted non-overlapping intervals. If the new interval overlaps
    with any of the existing intervals, merge them. Return the resulting list of intervals.
    """
    new_intervals = []
    new_interval_start, new_interval_end = new_interval
    for i, (start, end) in enumerate(current_intervals):
        if end < new_interval_start:
            new_intervals.append((start, end))
        elif start > new_interval_end:
            # Add the new interval and all remaining intervals
            new_intervals.append((new_interval_start, new_interval_end))
            return new_intervals + current_intervals[i:]
        else:
            # Intervals overlap or are adjacent, merge them
            new_interval_start = min(start, new_interval_start)
            new_interval_end = max(end, new_interval_end)

    # If we're here, the new/merged interval is the last one
    new_intervals.append((new_interval_start, new_interval_end))
    return new_intervals
