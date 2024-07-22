import os
from datetime import UTC, datetime

from utils.prepare import DEFAULT_MODE
from utils.type_utils import ChatMode

VERSION = "v0.2.5"
DELIMITER = "-" * 94 + "\n"
DELIMITER40 = "-" * 40 + "\n"
DELIMITER20 = "-" * 20

INTRO_ASCII_ART = """\
 ,___,   ,___,   ,___,                                                 ,___,   ,___,   ,___,
 [OvO]   [OvO]   [OvO]                                                 [OvO]   [OvO]   [OvO]
 /)__)   /)__)   /)__)               WELCOME TO DOCDOCGO               /)__)   /)__)   /)__)
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
    "/kb": ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
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
    "/export": ChatMode.EXPORT_COMMAND_ID,
    "/ex": ChatMode.EXPORT_COMMAND_ID,
    "/summarize": ChatMode.SUMMARIZE_COMMAND_ID,
    "/su": ChatMode.SUMMARIZE_COMMAND_ID,
    "/share": ChatMode.SHARE_COMMAND_ID,
    "/sh": ChatMode.SHARE_COMMAND_ID,
}

DEFAULT_CHAT_MODE = command_ids[DEFAULT_MODE]

GREETING_MESSAGE = """\
🦉**Hi, I'm DocDocGo!** With my signature _infinite research_, I can save you time when finding the information you need takes more than a quick Google search. I can comb through hundreds of sites, find which ones have relevant information, and:

- give you the aswer from each relevant source (_heatseek_ research mode)
- write a report using all sources, put them in a knowledge base for follow-up chat (_classic_ research)
"""

"""I have two research modes: 

- **Heatseek mode**: I keep looking for sites with the exact information you need
- **Classic mode**: I keep ingesting sites relevant to your query into a knowledge base to use when chatting

In heatseek mode, I give you candidate answers as I find them. In report mode, you get a report that combines insights from the ingested sources and a knowledge base for follow-up questions. 

"""

GREETING_MESSAGE = """\
👋**Hi, I'm DocDoc:green[Go]!** My superpower is **infinite research** - when you need to go beyond a quick Google search, I will comb through hundreds of websites looking for the information you need. I can:

- look for sources containing something specific you need (_heatseek_ research mode), or
- write a report using all sources and put them in a knowledge base for follow-up chat (_classic_ research)

"""

_older_draft2 = """\
🦉**Hi, I'm DocDocGo!** I can help when you need information that can't be found with a quick Google search. I can comb through hundreds of sites and:

- give you the answer from each relevant source (_heatseek_ research mode)
- write a report using all sources, put them in a knowledge base for follow-up questions (_classic_ research)

"""

_older_draft = """I have two research modes: 

- **Heatseek mode**: I keep looking for sites with the exact information you need
- **Classic mode**: I keep ingesting sites relevant to your query into a knowledge base to use when chatting

In heatseek mode, I give you candidate answers as I find them. In report mode, you get a report that combines insights from the ingested sources and a knowledge base for follow-up questions. 

"""

GREETING_MESSAGE_SUFFIX_DEFAULT = "I have lots of cool commands, but the only one to remember is: `/help <any question on using me>`"
# GREETING_MESSAGE_SUFFIX_DEFAULT = "I'm also _self-aware_ - I know how to use me, `/help <your question>`"
GREETING_MESSAGE_SUFFIX_OTHER = GREETING_MESSAGE_SUFFIX_DEFAULT
# "How? Just ask me by typing `/help <your question>`."

WALKTHROUGH_TEXT = """\
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
- `/research heatseek Find a code snippet for a row of buttons in Streamlit`

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
    - I can keep researching more and more sources and improving my report iteratively
    - I **save sources** in a new doc collection, so you can ask me questions about them
- **Summarize** a web page and ingest it into a collection

### How to use me

First things first, I know figuring out how to use a new tool can be a bit overwhelming. But don't \
worry, you won't have to memorize all the commands. Instead, you can just type `/help` followed by \
what you want to do, and I'll guide you through it. For example:

```markdown
/help How can I have you do web research for me?
```

Now let's go over my features and commands. The general pattern for queries is to enter one of the prefixes below followed by your message. Different prefixes activate my different capabilities. A prefix is optional - messages with no prefix by default get treated as regular chat using the current collection as a knowledge base.

Here's what each prefix does. Most important ones:

- `/kb <your query>`: chat using the current collection as a knowledge base
- `/research <your query>`: do "classic" research - ingest websites into a collection, write a report
- `/research heatseek <your query>`: do "heatseek" research - find websites that contain the answer
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
- `/export`: export your data

Ingesting into the current vs a new collection:

- `/ingest new <with or without URL>`: ingest into a new collection
- `/ingest add <with or without URL>`: ingest and add to the current collection
- `/summarize <new/add> <URL>`: same rules in regards to `new`/`add`

The default behavior (if `new`/`add` is not specified) is to (a) normally ingest into a new collection, which is given a special name (`ingested-content-...`); (b) if the current collection has this kind of name, add to it. That way, you can use `/ingest` several times in a row and all the documents will be added to the same collection.

Example queries (you can try them out in sequence):

- `/help What in the world is infinite research?`
- `/research What are this month's most important AI news?`
- `/research` (to see research options)
- `/research deeper` (to expand the research to cover more sources)
- `/re deeper` (same - first two letters of a command are enough)
- `/kb Which news you found relate to OpenAI`
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
- `/db list bla`: list your collections whose names contain "bla"
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"
- `/db status`: show your access level for the current collection and related info
- `/db`: show database management options

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db list 42+`: list collections starting from #42
- `/db list bla*`: list collections whose names start with "bla"
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

EXPORT_COMMAND_HELP_MSG = """\
To export your conversation, use the command:

- `/ex chat <optional number of past messages>` (or `/export` instead of `/ex`)

If the number of past messages is not specified, the entire conversation will be exported. If you want to export the messages in reverse order, use `/ex <optional number> reverse`.
"""

DESCRIPTION_FOR_HEALTH_UNIVERSE = """\
DocDocGo is more than just a chatbot, it's your tireless research assistant. It automates tasks that normally involve manually sifting through dozens (or hundreds!) of online resources in search of precious nuggets of relevant hard-to-find information. It can

- find hundreds of websites about your chosen topic/query and ingest into a knowledge base
- write a report on your topic/query based on the ingested content
- allow you to chat with the created knowledge base and ask any follow-up questions 
- search for an answer to a specific narrow question or hard-to-find piece of data by sifting through hundreds of Google search results
- create a knowledge base from your local documents (Word docs, PDFs, etc.)

Oh, and it's "self-aware" -  you can ask DocDocGo questions about itself and it will help you navigate its many features.

Basic usage:

1. Get help - if you are just starting out and not sure what to do, start with:

- `/help I heard you can help me with web research. How?`

2. Research a topic, get a report and build a knowledge base:

- `/research role of oxytocin in reptiles` - this does an initial round generates a report 
- `/re deeper` - roughly doubles the number of ingested sources and generates a new report
- `What studies about reptiles are in your knowledge base?` - chat with the knowledge base
- `/re deeper <optional number of doublings>` - keep doubling the number of ingested sources

 NOTE: There will be several intermediate reports produced as DDG performs its iterations, but you may wish to focus on the ones at the end of each "deepening" - they amalgamate all previous reports.

3. Look for something specific:

- `/re heatseek Find articles criticizing Vickers' meta-analysis of acupuncture for chronic pain`
- `/re heatseek 6` - perform 6 more iterations (each iteration looks at 2-5 websites)
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


def format_nonstreaming_answer(answer):
    return {"answer": answer, "needs_print": True}


def format_invalid_input_answer(answer, status_body):
    return {
        "answer": answer,
        "needs_print": True,
        "status.header": "Invalid input",
        "status.body": status_body,
    }


DEFAULT_TIMESTAMP_FORMAT = None  # iso
RESEARCH_TIMESTAMP_FORMAT = "%A, %B %d, %Y, %I:%M %p"
DB_CREATED_AT_TIMESTAMP_FORMAT = "%d-%b-%Y %I:%M %p"  # "%B %d, %Y, %I:%M%p UTC"


def get_timestamp(format: str | None = DEFAULT_TIMESTAMP_FORMAT):
    if format is None:
        return datetime.now(tz=UTC).isoformat()
    return datetime.now(tz=UTC).strftime(format)
    # "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),


def parse_timestamp(timestamp: str, format: str | None = DEFAULT_TIMESTAMP_FORMAT):
    if format is None:
        return datetime.fromisoformat(timestamp)
    return datetime.strptime(timestamp, format)
