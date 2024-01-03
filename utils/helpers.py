import os
from datetime import datetime

from utils.prepare import DEFAULT_COLLECTION_NAME, DEFAULT_MODE
from utils.type_utils import ChatMode

DELIMITER = "-" * 94 + "\n"
INTRO_ASCII_ART = """\
 ,___,   ,___,   ,___,                                                 ,___,   ,___,   ,___,
 [OvO]   [OvO]   [OvO]                                                 [OvO]   [OvO]   [OvO]
 /)__)   /)__)   /)__)               WELCOME TO DOC DOC GO             /)__)   /)__)   /)__)
--"--"----"--"----"--"--------------------------------------------------"--"----"--"----"--"--"""

MAIN_BOT_PREFIX = "DocDocGo: "

PRIVATE_COLLECTION_PREFIX = "u-"
PRIVATE_COLLECTION_USER_ID_LENGTH = 6

# The length of the prefix + the user ID (pre-calculated for efficiency)
PRIVATE_COLLECTION_FULL_PREFIX_LENGTH = (
    len(PRIVATE_COLLECTION_PREFIX) + PRIVATE_COLLECTION_USER_ID_LENGTH
)

# If bot tries to create a community collection with the above prefix, use:
SUBSTITUTE_FOR_PRIVATE_COLLECTION_PREFIX = "uu-"  # TODO implement this

command_ids = {
    "/chat": ChatMode.JUST_CHAT_COMMAND_ID,
    "/docs": ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
    "/details": ChatMode.DETAILS_COMMAND_ID,
    "/quotes": ChatMode.QUOTES_COMMAND_ID,
    "/web": ChatMode.WEB_COMMAND_ID,
    "/research": ChatMode.ITERATIVE_RESEARCH_COMMAND_ID,
    "/db": ChatMode.DB_COMMAND_ID,
    "/help": ChatMode.HELP_COMMAND_ID,
    "/ingest": ChatMode.INGEST_COMMAND_ID,
    "/upload": ChatMode.INGEST_COMMAND_ID,  # alias for /ingest
}

DEFAULT_CHAT_MODE = command_ids[DEFAULT_MODE]

GREETING_MESSAGE = """\
🦉**Hi, I'm DocDocGo!** I can chat with you like ChatGPT, and also can:
- research a topic on the web and write a report
- keep fetching more sources and rewriting the report iteratively
- answer follow-up questions using all the sources as a knowledge base
- answer questions about documents you provide

For more details you can jusk ask me! (or type `/help`) \
"""

EXAMPLE_QUERIES = """\
Here are some example queries (you can try them out in sequence):
- `/research What are this month's most important AI news?`
- `/research` (to fetch more websites and iterate on the previous report)
- `Bullet point for me just the ones related to OpenAI`
- `/db` (to manage your *collections*, i.e. the knowledge bases we've created)
- `/ingest` (to upload your own documents and create a new collection)
- `/db use docdocgo-documentation` (to switch to the default collection)
- `How can I get more help using you?`
"""

HELP_MESSAGE = f"""\
### What I can do

- **Answer questions** about documents you provide.
    - Documents are organized into **collections**
    - The chat box shows which collection is currently used for my answers
- **Research a topic** on the web and generate a report
    - I can keep researching more and more sources and improving my report iteratively.
    - I **save sources** in a new doc collection, so you can ask me questions about them.

### How to use me

You can enter your messages with or without a prefix. Different prefixes activate my different \
response modes. Think of them like different subagents, each with a different job. \
The default mode is `{DEFAULT_MODE}`.

Here's what each prefix does. Most important prefixes:
- `/ingest` or `/upload`: upload your documents and ingest them into a collection
- `/research`: perform iterative Internet research (no message = iterate on previous report)
- `/docs`: chat with me about your currently selected doc collection (or a general topic)
- `/db`: manage your doc collections (select, rename, etc.)

Other prefixes:
- `/help`: show this help message
- `/details`: get details about the retrieved documents
- `/quotes`: get quotes from the retrieved documents
- `/web`: perform web searches and generate a report
- `/chat`: regular chat, without retrieving docs or websites

Example queries: 
- `/research What are this month's most important AI news?`
- `/research` (to fetch more websites and iterate on the previous report)
- `/docs Bullet point for me just the ones related to OpenAI`
- `/db` (to manage collections)

If you're in a reading mood, here's a [link to my full docs]\
(https://github.com/reasonmethis/docdocgo-core/blob/main/README.md).

Or simply ask me for help! By default, I'm set up to use the `docdocgo-documentation` \
collection. As long as it's selected in the chatbox below, I'll know how to use me.

> If you need to switch to the default collection, type `/db use docdocgo-documentation`.
"""

DB_COMMAND_HELP_TEMPLATE = f"""\
Your current document collection is: `{{current_db}}`

You can use the following commands to manage your collections:
- `/db list`: list all your collections
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"

Here are some additional shorthands:
- `/db use 3`: switch to collection #3 in the list
- `/db delete --current` (or just `-c`): delete the current collection

Remember, you can always ask me for help in using me - you just need to make sure that \
the default collection (`{DEFAULT_COLLECTION_NAME}`) is selected.
"""


def print_no_newline(*args, **kwargs):
    """
    Print without adding a newline at the end
    """
    print(*args, **kwargs, end="", flush=True)


def is_directory_empty(directory):
    return not os.listdir(directory)


def clear_directory(directory):
    """
    Remove all files and subdirectories in the given directory.
    """
    import shutil

    errors = []
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        except Exception as e:
            errors.append(e)
    if errors:
        err_str = "\n".join([str(e) for e in errors])
        raise Exception("Could not delete all items:\n" + err_str)


def lin_interpolate(x, x_min, x_max, y_min, y_max):
    """Given x, return y that linearly interpolates between two points
    (x_min, y_min) and (x_max, y_max)"""
    return y_min + (y_max - y_min) * (x - x_min) / (x_max - x_min)


def clamp(value, min_value, max_value):
    """Clamp value between min_value and max_value"""
    return max(min_value, min(value, max_value))


def utc_timestamp_int() -> int:
    """Returns the current UTC timestamp as an integer (seconds since epoch)"""
    return int(datetime.utcnow().timestamp())
