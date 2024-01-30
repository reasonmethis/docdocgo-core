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
    "/ch": ChatMode.JUST_CHAT_COMMAND_ID,
    "/docs": ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
    "/do": ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
    "/details": ChatMode.DETAILS_COMMAND_ID,
    "/de": ChatMode.DETAILS_COMMAND_ID,
    "/quotes": ChatMode.QUOTES_COMMAND_ID,
    "/qu": ChatMode.QUOTES_COMMAND_ID,
    "/web": ChatMode.WEB_COMMAND_ID,
    "/we": ChatMode.WEB_COMMAND_ID,
    "/research": ChatMode.RESEARCH_COMMAND_ID,
    "/re": ChatMode.RESEARCH_COMMAND_ID,
    "/db": ChatMode.DB_COMMAND_ID,
    "/help": ChatMode.HELP_COMMAND_ID,
    "/ingest": ChatMode.INGEST_COMMAND_ID,
    "/in": ChatMode.INGEST_COMMAND_ID,  
    "/upload": ChatMode.INGEST_COMMAND_ID,  # alias for /ingest
    "/up": ChatMode.INGEST_COMMAND_ID,  
    # "/browse": ChatMode.BROWSE_COMMAND_ID,
}

DEFAULT_CHAT_MODE = command_ids[DEFAULT_MODE]

GREETING_MESSAGE = """\
🦉**Hi, I'm DocDocGo!** I can chat with you like ChatGPT, and also can:
- research a topic on the web for as long as you want and generate a report
- chat using all sources fetched during research as a knowledge base
- similarly chat using documents you provide as a knowledge base

How? Just ask me! (or type `/help`) \
"""

EXAMPLE_QUERIES = """\
To showcase some of my talents, feel free to try the following queries in sequence:
- `/research legal arguments for and against disqualifying Trump from running`
- `/research deeper` (to fetch more sites and make a new report based on 2x as many sources)
- `What legal scholars have argued for disqualification?`
- `/db use 1` (to switch to the default collection, which contains DocDocGo's documentation)
- `How can I do "infinite" research? Tell me in the style of prof. Dumbledore.`
- `/db` (to manage your _collections_, i.e. the knowledge bases we've created)
- `/ingest` (to upload your own documents and create a new collection)

After performing the "deeper" command above, you will end up with a report that uses \
information from 2x as many sources as the original report. If you wanted to quadruple \
the number of sources, you could use `/research deeper 2` instead. 

:grey[**Tip:** Swiching from GPT 3.5 to 4 (in the sidebar) improves my performance. \
You'll need your own OpenAI API key for that. Using your own key also relaxes the restriction \
on the maximum number of automatic research iterations.]
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

- `/research`: perform "infinite" Internet research, ingesting websites into a collection
- `/ingest` or `/upload`: upload your documents and ingest them into a collection
- `/docs <your query>`: chat with me about your currently selected doc collection (or a general topic)
- `/db`: manage your doc collections (select, rename, etc.)

Other prefixes:

- `/help`: show this help message
- `/details <your query>`: get details about the retrieved documents
- `/quotes <your query>`: get quotes from the retrieved documents
- `/web <your query>`: perform web searches and generate a report
- `/chat <your query>`: regular chat, without retrieving docs or websites

Example queries:

- `/research What are this month's most important AI news?`
- `/research` (to see research options, including the "infinite" research)
- `/research deeper` (to expand the research to cover more sources)
- `/re deeper` (same - first two letters of a command are enough)
- `/docs Tell me just the ones related to OpenAI`
- `/chat Reformat your previous answer as a list of short bullet points`

If you're in a reading mood, here's a [link to my full docs]\
(https://github.com/reasonmethis/docdocgo-core/blob/main/README.md).

Or simply ask me for help! By default, I'm set up to use the `docdocgo-documentation` \
collection. As long as it's selected in the chatbox below, I'll know how to use me.

> If you need to switch to the default collection, you can use the shorthand `/db use 1`.
"""

DB_COMMAND_HELP_TEMPLATE = f"""\
Your current document collection is: `{{current_db}}`

You can use the following commands to manage your collections:

- `/db list`: list all your collections
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db delete 3, 42, 12`: delete collections #3, #42, and #12 (be careful!)
- `/db delete --current` (or just `-c`): delete the current collection

Remember, you can always ask me for help in using me - you just need to make sure that \
the default collection (`{DEFAULT_COLLECTION_NAME}`) is selected. If it isn't, type \
`/db use 1`.\
"""

RESEARCH_COMMAND_HELP_MESSAGE = """\
Here are the most important commands you can use for Internet research:

- `/research <your query>`: start new Internet research, generate report, create KB from fetched sites
- `/research deeper`: expand report and KB to cover 2x more sites as current report
- `/research deeper 3`: perform the above 3 times (careful - time/number of steps increases exponentially)

You can also use the following commands:

- `/research new <your query>`: same as without `new` (can use if the first word looks like a command)
- `/research more`: keep original query, but fetch more websites and create new report version
- `/research combine`: combine reports to get a report that takes more sources into account
- `/research auto 42`: performs 42 iterationso of "more"/"combine"
- `/research iterate`: fetch more websites and iterate on the previous report
- `/research <cmd> 42`: repeat command such as `more`, `combine`, etc. 42 times

You can also view the reports:

- `/research view main`: view the main report (`main` can be omitted)
- `/research view stats`: view just the report stats
- `/research view base`: view the base reports
- `/research view combined`: view the combined reports
"""
# - `/research more <your new query>`: same as above, but ingest into current collection


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


def format_nonstreaming_answer(answer):
    return {"answer": answer, "needs_print": True}


def format_invalid_input_answer(answer, status_body):
    return {
        "answer": answer,
        "needs_print": True,
        "status.header": "Invalid input",
        "status.body": status_body,
    }
