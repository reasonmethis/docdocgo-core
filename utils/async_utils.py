import asyncio


def make_sync(async_func):
    """
    Make an asynchronous function synchronous.
    """
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(async_func(*args, **kwargs))
    return wrapper

# Other approaches:
# asyncio.run(async_func(*args, **kwargs))
#
# from concurrent.futures import ThreadPoolExecutor
#     with ThreadPoolExecutor() as executor:
#         future = executor.submit(asyncio.run, async_func(*args, **kwargs))
#         return future.result()


def run_task_sync(task):
    """
    Run an asyncio task synchronously.
    """
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(task)

def gather_tasks_sync(tasks):
    """
    Run a list of asyncio tasks synchronously.
    """
    return run_task_sync(asyncio.gather(*tasks))