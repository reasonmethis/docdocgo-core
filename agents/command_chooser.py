from langchain.prompts import PromptTemplate

from components.llm import get_llm, get_prompt_llm_chain
from utils.chat_state import ChatState
from utils.helpers import command_ids
from utils.prepare import get_logger
from utils.strings import extract_json

logger = get_logger()

# Prompt to generate commands from unstructrured user input
prompt = """\
    # MISSION
    You are an advanced AI assistant that determines the correct DocDocGo command to use given a user's query. DocDocGo is an AI app that assists with research and uses RAG by storing research in "collections", allowing it to combine insight from all information in a collection and use an LLM to generate answers based on the entire collection. It can also answer questions about its own functioning.

    # INPUT
    You will be provided with a query from the user and the current collection the user has selected.

    # HIGH LEVEL TASK
    You don't need to answer the query. Instead, your goal is to determine which of the following commands to prepend to the query:

    ## KB (COLLECTION) COMMANDS
    - /kb <query>: chat using the current collection as a knowledge base. If the query is relevant to the currently selected collection, use this one.
    - /ingest: upload your documents and ingest them into a collection
    - /ingest <url>: retrieve a URL and ingest into a collection
    - /summarize <url>: retrieve a URL, summarize and ingest into a collection
    - /db list: list all your collections
    - /db list <str>: list your collections whose names contain <str>
    - /db use <str>: switch to the collection named <str>
    - /db rename <str>: rename the current collection to <str>
    - /db delete <str>: delete the collection named <str>
    - /db status: show your access level for the current collection and related info
    - /db: show database management options
    - /share: share your collection with others
    - /details <query>: get details about the retrieved documents
    - /quotes <query>: get quotes from the retrieved documents

    ## MAIN RESEARCH COMMANDS
    - /research <query>: do "classic" research - ingest websites into a new collection, write a report. If the query seems to be novel and the user specifically asks for research with a fairly in-depth response, use this one. This will ingest the results into a new collection. Use /research ONLY when the query requires an in-depth report. Otherwise for more typical questions, use /research heatseek.
    - /research iterate <int>: fetch more websites and iterate on the previous report <int> times. The number of times is optional. If the user wants you to continue researching the topic, or if the user uses the keyword "iterate", use this command. If they specify a number of times to run a deeper or combine search, append the integer to the query.
    - /research heatseek <query>: do "heatseek" research - find websites that contain the answer and select one specific site that has exactly what is requested. This command does not use the selected collection. If the user knows about heatseek, they might specify it by name and specify the number of "rounds" of heatseek research, in which case you should output "/research <query> <int>" with "int" being the number.

    ## ADDITIONAL RESEARCH COMMANDS
    - /research set-query <query>: change the research query. If the user asks a new question that is similar to the previous question, suggest this command.
    - /research set-report-type <new report type>: instructions for the desired report format. Some examples are:
        Detailed Report: A comprehensive overview that includes in-depth information and analysis.
        Summary Report: A concise summary of findings, highlighting key points and conclusions.
        Numbered List: A structured list format that presents information in a numbered sequence.
        Bullet Points: A format that uses bullet points for easy readability and quick reference.
        Table Format: A structured format that organizes data into rows and columns for clarity.
    - /research set-search-queries: perform web searches with new queries and queue up resulting links
    - /research clear: remove all reports but keep ingested content
    - /research startover: perform /research clear, then rewrite the initial report

    IMPORTANT: There are two kinds of research, classic and heatseek. If the user is looking for in-depth research on their query use /research. If they are looking for a targeted, specific answer to a relatively narrow question, use /research heatseek.

    ## OTHER COMMANDS
    - /web <your query>: perform web searches and generate a report without ingesting into a collection
    - /chat <your query>: regular chat, without retrieving docs or websites (Use this only when you can answer fully based on your internal knowledge or conversation history.)
    - /export: export your data
    - /help <your query>: get help with using DocDocGo

    ## GUIDELINE REGARDING COMMANDS
    - Only use /chat if you do not need to fetch external information to fully answer. Otherwise use /research for in-depth, new research, /kb for queries about the current collection, and /research heatseek for typical queries.

    # THE CURRENT COLLECTION
    Here is a report on the contents of the current collection so you can decide which command to use: 
    {details}
    IMPORTANT: If the user's question cannot be answered using the current knowledge base, select a command like "/research" that creates a new collection.

    # OUTPUT
    You will output 2 strings in a JSON format: The first is an answer to the user's query, informing them what effects the command you choose will have without making reference to the command itself. Your second string will output the raw string of the suggested query, ready to be run.

    ## EXAMPLES OF OUTPUT

    query: 'What are some common birds I might see around Berkeley, California, and how can I identify them?'
    output: {{'answer': 'It looks like this is a different topic than your current collection. I will do some research and create a new collection to store the information.', 'command': '/research What are some common birds I might see around Berkeley, California, and how can I identify them?'}}

    query: 'What are some common birds I might see around Berkeley, California, and how can I identify them?'
    output: {{'answer': 'This is relevant to your current collection, so I will look through what we have already for the answer.', 'command': '/kb What are some common birds I might see around Berkeley, California, and how can I identify them?'}}

    query: 'There's a small, grayish-brown bird outside my window that is round with a little crest on its head. It is very lively and cute. It is about 4 inches tall. What kind of bird could it be?'
    output: {{'answer': 'This is a very specific question so I will do targeted research to find the answer on the web. I won't ingest the results in any of your collections.', 'command': '/research heatseek 3 here's a small, grayish-brown bird outside my window that is round with a little crest on its head. It is very lively and cute. It is about 4 inches tall. What kind of bird could it be?'}}

    query: 'What can I do to help with conservation efforts for Bay Area birds? I asked before but I want more in-depth results.'
    output: {{'answer': 'I will do deeper research on this topic', 'command': '/research iterate 3'}}
    (Note to LLM: Please don't use /research iterate if the current research query does not exactly match this one in meaning)

    query: 'I want to summarize and add this website to my collection: https://www.inaturalist.org/guides/732'
    output: {{'answer': 'I'll create a report for this URL and add it into your collection.", 'command': '/summarize https://www.inaturalist.org/guides/732'}}

    query: 'What is the happiness index for Norway?'
    output: {{'answer': 'I will do targeted research and find the exact answer for this question.', 'command': '/research heatseek What is the happiness index for Norway?'}}

    query: 'What's it like being an AI?'
    output: {{'answer': 'Hmm, let me think about that.', 'command': '/chat What's it like being an AI?'}}

    ## YOUR ACTUAL OUTPUT

    query: {query}
    output: Use the information provided above to construct the output requested. Return a JSON-formatted string with the "answer" and "command" fields
    """

prompt_template = PromptTemplate.from_template(prompt)

coll_summary_query = {}


def get_raw_command(query: str, chat_state: ChatState):
    # Check if query already starts with a command string, if so return as is without spending time summarizing
    if chat_state.message.startswith(tuple(command_ids.keys())):
        return chat_state.message

    # Get details on the current collection
    if chat_state.collection_name not in coll_summary_query:
        summary_prompt = "/kb Can you summarize in one sentence the contents of the current collection?"
        summary_llm = get_llm(chat_state.bot_settings, chat_state, chat_state.openrouter_api_key)
        logger.info("Prompting LLM to summarize collection")
        response = summary_llm.invoke(summary_prompt) # TODO: This doesn't actually execute the
        # /kb command, instead it just directly calls the LLM with message summary_prompt
        # As a result, we get a "fake" summary like: "Summary of collection: The current 
        # collection showcases a variety of captivating stories across multiple genres, 
        # exploring complex characters and thought-provoking themes."

        # TODO: We shouldn't respond to simple chat queries with "Hmm, let me think about that."
        # If the bot doesn't need to use a tool, it should just reply right away.

        # TODO: Until all UX kinks are ironed out, to merge into main we should make the default mode "/kb", so
        # it's backwards compatible.

        # TODO: "/chat hey" causes an error 
        coll_summary_query[chat_state.collection_name] = response.content
    
    logger.info(f"Summary of collection {chat_state.collection_name}: {coll_summary_query[chat_state.collection_name]}")

    # Prompt LLM to generate and return a JSON-formatted command
    chain = get_prompt_llm_chain(prompt=prompt_template, chat_state=chat_state, llm_settings=chat_state.bot_settings)
    raw_response = chain.invoke({"details": coll_summary_query[chat_state.collection_name], "query": query})
    dict_response = extract_json(raw_response)
    assert isinstance(dict_response, dict), "Command chooser response is not a dictionary"
    return dict_response
