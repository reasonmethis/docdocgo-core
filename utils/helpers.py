import os
from datetime import datetime, UTC

from utils.prepare import DEFAULT_MODE
from utils.type_utils import ChatMode

DELIMITER = "-" * 94 + "\n"
DELIMITER40 = "-" * 40 + "\n"
INTRO_ASCII_ART = """\
 ,___,   ,___,   ,___,                                                 ,___,   ,___,   ,___,
 [OvO]   [OvO]   [OvO]                                                 [OvO]   [OvO]   [OvO]
 /)__)   /)__)   /)__)               WELCOME TO DOC DOC GO             /)__)   /)__)   /)__)
--"--"----"--"----"--"--------------------------------------------------"--"----"--"----"--"--"""

MAIN_BOT_PREFIX = "DocDocGo: "

PRIVATE_COLLECTION_PREFIX = "u-"
PRIVATE_COLLECTION_PREFIX_LENGTH = len(PRIVATE_COLLECTION_PREFIX)
PRIVATE_COLLECTION_USER_ID_LENGTH = 6

# The length of the prefix + the user ID (pre-calculated for efficiency)
PRIVATE_COLLECTION_FULL_PREFIX_LENGTH = (
    PRIVATE_COLLECTION_PREFIX_LENGTH + PRIVATE_COLLECTION_USER_ID_LENGTH
)  # does not include the hyphen btw prefix and collection name

# If bot tries to create a community collection with the above prefix, use:
SUBSTITUTE_FOR_PRIVATE_COLLECTION_PREFIX = "uu-"  # TODO implement this

ADDITIVE_COLLECTION_PREFIX = "ingested-content"
INGESTED_DOCS_INIT_PREFIX = "ingested-content-rename-me-"

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
    "/he": ChatMode.HELP_COMMAND_ID,
    "/ingest": ChatMode.INGEST_COMMAND_ID,
    "/in": ChatMode.INGEST_COMMAND_ID,
    "/upload": ChatMode.INGEST_COMMAND_ID,  # alias for /ingest
    "/up": ChatMode.INGEST_COMMAND_ID,
    "/summarize": ChatMode.SUMMARIZE_COMMAND_ID,
    "/su": ChatMode.SUMMARIZE_COMMAND_ID,
    "/share": ChatMode.SHARE_COMMAND_ID,
    "/sh": ChatMode.SHARE_COMMAND_ID,
}

DEFAULT_CHAT_MODE = command_ids[DEFAULT_MODE]

GREETING_MESSAGE = """\
🦉**Hi, I'm DocDocGo!** I can chat with you like ChatGPT, and also can:
- research a topic on the web for as long as you want and generate a report
- chat using all sources fetched during research as a knowledge base
- similarly chat using documents you provide as a knowledge base

"""

GREETING_MESSAGE_PREFIX_DEFAULT = "How? Just ask me! (or type `/help`)"
GREETING_MESSAGE_PREFIX_OTHER = "How? Just ask me by typing `/help <your question>`."

EXAMPLE_QUERIES = """\
To showcase some of my talents, feel free to try the following queries in sequence:
- `/summarize https://blog.rwkv.com/p/eagle-7b-soaring-past-transformers`
- `Explain the main point like I'm in high school`
- `/db delete --current` (to discard the newly created knowledge base aka _collection_)
- `/research legal arguments for and against disqualifying Trump from running`
- `/research deeper` (to fetch more sites and make a new report based on 2x as many sources)
- `Which legal scholars have argued for disqualification?`
- `/help How can I do "infinite" research? Tell me like you are prof. Dumbledore`
- `/db` (to manage your _collections_, i.e. the knowledge bases we've created)
- `/ingest` (to upload your own documents and create a new collection)
- `/research heatseek Find me a quote by Obama about Jill Biden`

After performing the "deeper" command above, you will end up with a report that uses \
information from 2x as many sources as the original report. If you wanted to quadruple \
the number of sources, you could use `/research deeper 2` instead. 

:grey[**Tip:** Swiching from GPT 3.5 to 4 (in the sidebar) improves my performance. \
You'll need your own OpenAI API key for that. Using your own key also relaxes the restriction \
on the maximum number of automatic research iterations.]
"""

HELP_MESSAGE = """\
### What I can do

- **Answer questions** about documents you provide.
    - Documents are organized into **collections**
    - The chat box shows which collection is currently used for my answers
- **Research a topic** on the web and generate a report
    - I can keep researching more and more sources and improving my report iteratively.
    - I **save sources** in a new doc collection, so you can ask me questions about them.
- **Summarize** a web page and ingest it into a collection

### How to use me

First things first, I know figuring out how to use a new tool can be a bit overwhelming. But don't \
worry, you won't have to memorize all the commands. Instead, you can just type `/help` followed by \
what you want to do, and I'll guide you through it. For example:

```markdown
/help How can I have you do web research for me?
```

Now let's go over my features and commands. The general pattern for queries is to enter one of the prefixes below followed by your message. Different prefixes activate my different capabilities. A prefix is optional - if you just enter a message the default `/docs` prefix is used.

Here's what each prefix does. Most important ones:

- `/research <your query>`: perform "infinite" Internet research, ingesting websites into a collection
- `/research heatseek <your query>`: perform "heatseek" research - find websites that contain the answer
- `/docs <your query>`: chat about your currently selected doc collection (or a general topic)
- `/ingest`: upload your documents and ingest them into a collection
- `/ingest https://some.url.com`: retrieve a URL and ingest into a collection
- `/summarize https://some.url.com`: retrieve a URL, summarize and ingest into a collection
- `/db`: manage your doc collections (select, rename, etc.)
- `/share`: share your collection with others
- `/help <your question>`: ask me about how to use me

Other prefixes:

- `/details <your query>`: get details about the retrieved documents
- `/quotes <your query>`: get quotes from the retrieved documents
- `/web <your query>`: perform web searches and generate a report without ingesting
- `/chat <your query>`: regular chat, without retrieving docs or websites

Ingesting into the current vs a new collection:

- `/ingest new <with or without URL>`: ingest into a new collection
- `/ingest add <with or without URL>`: ingest and add to the current collection

The default behavior (if `new`/`add` is not specified) is to (a) normally ingest into a new collection, which is given a special name (`ingested-content-...`); (b) if the current collection has this kind of name, add to it. That way, you can use `/ingest` several times in a row and all the documents will be added to the same collection.

Example queries (you can try them out in sequence):

- `/help What in the world is infinite research?`
- `/research What are this month's most important AI news?`
- `/research` (to see research options, including the "infinite" research)
- `/research deeper` (to expand the research to cover more sources)
- `/re deeper` (same - first two letters of a command are enough)
- `/docs Which news you found relate to OpenAI`
- `/chat Reformat your previous answer as a list of short bullet points`
- `/re heatseek 3 I need example code for how to update React state in shadcn Slider component`

If you're in a reading mood, here's a [link to my full docs]\
(https://github.com/reasonmethis/docdocgo-core/blob/main/README.md).

Or simply ask me for help! I have "digested" my own documentation, so I can help you find \
what you need. Just type `/help` followed by your question.\
"""

DB_COMMAND_HELP_TEMPLATE = """\
Your current document collection's full name: `{current_db}`

You can use the following commands to manage your collections:

- `/db list`: list all your collections
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"
- `/db status`: show your access level for the current collection and related info

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db delete 3, 42, 12`: delete collections #3, #42, and #12 (be careful!)
- `/db delete --current` (or just `-c`): delete the current collection

Remember, you can always ask me for help in using me - simply type `/help` followed by your question.\
"""

RESEARCH_COMMAND_HELP_MSG = """\
**1. "Heatseek" mode:** look for websites that contain the answer to your query (no KB created)

- `/research heatseek 6 <your query>`: perform 6 rounds of "heatseek" research
- `/re hs 5`: perform 5 more rounds (can use shorthands for commands)

This is a new, more lightweight mode that is highly useful when you need to find that "gem" of a website that contains some specific information and Google is just giving you too much noise.

**2. Regular mode:** use content from multiple websites to write a detailed answer, create a KB

- `/research <your query>`: start new research, generate report, create KB from fetched sites
- `/research deeper`: expand report and KB to cover 2x more sites as current report
- `/research deeper 3`: perform the above 3 times (careful - time/number of steps increases exponentially)

You can also use the following commands:

- `/research new <your query>`: same as without `new` (can use if the first word looks like a command)
- `/research more`: keep original query, but fetch more websites and create new report version
- `/research combine`: combine reports to get a report that takes more sources into account
- `/research auto 42`: performs 42 iterationso of "more"/"combine"
- `/research iterate`: fetch more websites and iterate on the previous report
- `/research <cmd> 42`: repeat command such as `more`, `combine`, `iterate`, etc. 42 times
- `/research set-query <your query>`: change your research query
- `/research set-report-type <new report type>`: instructions for the desired report format
- `/research set-search-queries`: perform web searches with new queries and queue up resulting links
- `/research clear`: remove all reports but keep ingested content
- `/research startover`: perform `/research clear`, then rewrite the initial report

You can also view the reports:

- `/research view main`: view the stats and main report (`main` can be omitted)
- `/research view stats`: view just the report stats
- `/research view base`: view the base reports
- `/research view combined`: view the combined reports

Remember, you can always ask me for help in using me - simply type `/help` followed by your question.\
"""
# - `/research more <your new query>`: same as above, but ingest into current collection

SHARE_COMMAND_HELP_MSG = """\
If you have owner-level access to the current collection, you can use the following commands to share it with others:

- `/share viewer pwd <any letters or numbers>`: give viewer access to the current collection
- `/share editor pwd <any letters or numbers>`: give editor access to the current collection
- `/share owner pwd <any letters or numbers>`: give owner access to the current collection

You can also revoke access:

- `/share revoke pwd <any letters or numbers>`: revoke a specific access code
- `/share revoke all-pwds`: revoke all access codes
- `/share revoke user <user ID>`: revoke access for a specific user
- `/share revoke all-users`: revoke access for all users
- `/share delete ...`: same as `revoke`

What is the difference between _viewer_, _editor_, and _owner_?

- _viewer_ can interact with the collection only in a way that does not modify it. For example, they can ask questions about its contents.
- _editor_ can perform actions that modify the collection, for example by ingesting new documents into it. They can't, however, rename, delete, or share the collection.
- _owner_ has unrestricted access to the collection

After you enter your command as described above, you will get a link that you can share with others. If you go with the `pwd` option, the recipient will always need to use that link to access the collection. If you opt for the `unlock-code` option (not yet implemented), the recipient will only need to use the link once, and then they will be able to access the collection without it.

**Tip:** If you have owner access to a collection, you can use `/db status` to see the access level of other users.\
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
    return int(datetime.now(UTC).timestamp())


def format_nonstreaming_answer(answer):
    return {"answer": answer, "needs_print": True}


def format_invalid_input_answer(answer, status_body):
    return {
        "answer": answer,
        "needs_print": True,
        "status.header": "Invalid input",
        "status.body": status_body,
    }

def get_timestamp():
    return datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
    # "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
