import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# NOTE: consider using async_to_sync from asgiref.sync library


def run_task_sync(task):
    """
    Run an asyncio task (more precisely, a coroutine object, such as the result of
    calling an async function) synchronously.
    """
    # print("-" * 100)
    # try:
    #     print("=" * 100)
    #     asyncio.get_running_loop()
    #     print("*-*" * 100)
    # except RuntimeError as e:
    #     print("?" * 100)
    #     print(e)
    #     print("?" * 100)
        # res = asyncio.run(task)  # no preexisting event loop, so run in the main thread
        # print("!" * 100)
        # print(res)
        # print("!" * 100)
        # return res
        # TODO: consider a situation when there is a non-running loop

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, task)
        return future.result()


def make_sync(async_func):
    """
    Make an asynchronous function synchronous.
    """

    def wrapper(*args, **kwargs):
        return run_task_sync(async_func(*args, **kwargs))

    return wrapper


def gather_tasks_sync(tasks):
    """
    Run a list of asyncio tasks synchronously.
    """

    async def coroutine_from_tasks():
        return await asyncio.gather(*tasks)

    return run_task_sync(coroutine_from_tasks())


def execute_func_map_in_processes(func, inputs, max_workers=None):
    """
    Execute a function on a list of inputs in a separate process for each input.
    """
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, inputs))
    
def execute_func_map_in_threads(func, inputs, max_workers=None):
    """
    Execute a function on a list of inputs in a separate thread for each input.
    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, inputs))
