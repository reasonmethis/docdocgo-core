import json
from pydantic import BaseModel, Field

from agentblocks.collectionhelper import (
    construct_new_collection_name,
    ingest_into_collection,
)
from agentblocks.core import enforce_pydantic_json
from agentblocks.docconveyer import DocConveyer
from agentblocks.webprocess import URLConveyer
from agentblocks.websearch import (
    get_links_from_queries,
    get_web_search_queries_from_prompt,
)
from utils.chat_state import ChatState
from utils.helpers import DELIMITER40, format_nonstreaming_answer, get_timestamp
from utils.prepare import CONTEXT_LENGTH, get_logger
from utils.strings import has_which_substring
from utils.type_utils import JSONishDict, Props
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

logger = get_logger()

query_generator_template = """# MISSION
You are an advanced assistant in satisfying USER's information need.

# INPUT 
You will be provided with a query from USER and the current timestamp.

# HIGH LEVEL TASK
You don't need to answer the query. Instead, your goal is to determine the information need behind the query and figure out the best possible Google search queries to find the best website that contains what USER needs.

# OUTPUT
Your output should be JSON in the following format:

{{"queries": [<array of 3-7 Google search queries that would be most helpful to perform in order to find the best single website that contains the perfect objective, unbiased, up-to-date answer to USER's query>]}}

## EXAMPLES OF OUTPUT 

query: "How do I start with Langchain? I want to use it to make a chatbot that I can deploy on a website."
timestamp: Thursday, March 13, 2025, 04:40 PM

output: {{"queries": ["langchain chatbot tutorial March 2025", "langchain getting started chatbot", "deploy langchain chatbot on website"]}}

query: "openai news"
timestamp: Saturday, June 22, 2024, 11:01 AM

output: {{"queries": ["openai news June 22 2024", "news about OpenAI June 2024", "recent OpenAI developments"]}}

query: "how can I merge two dictionaries in python?"
timestamp: Saturday, November 08, 2025, 06:04 PM

output: {{"queries": ["python merge dictionaries", "python 2025 dictionary union"]}}

query: "could you tell me the best way to treat chronic migraines"
timestamp: Monday, August 12, 2024, 11:15 PM

output: {{"queries": ["chronic migraines treatment", "evidence-based modern chronic migraine treatments", "science-based treatment chronic migraine 2024", "chronic migraines recent research August 2024"]}}

query: "I need a code example of how to use Slider shadcn/ui component in React that shows how to update state"
timestamp: Tuesday, September 12, 2023, 07:39 AM

output: {{"queries": ["shadcn ui Slider example", "shadcn \\"Slider\\" component React state update", "shadcn \\"Slider\\" controlled component React example", \\"Slider\\" uncontrolled component React example", "shadcn ui Slider tutorial"]}}

# YOUR ACTUAL OUTPUT
query: "{query}"
timestamp: {timestamp}

output: """
hs_query_generator_prompt = PromptTemplate.from_template(query_generator_template)

search_queries_updater_template = """\
You are an advanced assistant in satisfying USER's information need.

# High Level Task

You will be provided information about USER's query and current answer drafts. Your task is to determine what needs to be added or improved in order to better satisfy USER's information need and strategically design a list of google search queries that would be most helpful to perform.

# Input

1. USER's query: {query} 
END OF USER's query 

2. Current timestamp: {timestamp}
END OF timestamp

3. Past Google search queries used to generate the drafts of the answer: {past_search_queries}
END OF search queries

4. Past answer drafts and evaluations: 
{past_answers}
END OF past answers (the goal is to achieve evaluations of "EXCELLENT")

# Detailed Task

Let's work step by step. First, you need to determine what needs to be added or improved in order to better satisfy USER's information need. Then, based on the results of your analysis, you need to strategically design a list of google search queries that would be most helpful to perform to get an accurate, complete, unbiased, up-to-date answer. Design these queries so that the google search results will provide the necessary information to fill in any gaps in the current drafts of the answer, or improve them in any way.

Use everything you know about information foraging and information literacy in this task.

# Output

Your output should be in JSON in the following format:

{{"analysis": <brief description of what kind of information we should be looking for to improve the answer and why you think the previous google search queries may not have yielded that information>,
"queries": [<array of 3-7 new google search queries that would be most helpful to perform, based on that analysis>]}}

# Example

Suppose the user wants to get a numbered list of top Slavic desserts and you notice that the current answer drafts include desserts from Russia and Ukraine, but are missing desserts from other, non-former-USSR Slavic countries. You would then provide appropriate analysis and design new google search queries to fill in that gap, for example your output could be:

{{"analysis": "The current answers are missing desserts from other Slavic countries besides Russia and Ukraine. The current search queries seem to have resulted in content being mostly about countries from the former USSR so we should specifically target other Slavic countries.",
"queries": ["top desserts Poland", "top desserts Czech Republic", "top desserts Slovakia", "top desserts Bulgaria", "best desserts from former Yugoslavia", "desserts from Easern Europe"]}}

# Your actual output

Now, use the information in the "# Input" section to construct your actual output, which should start with the opening curly brace and end with the closing curly brace:

"""
hs_query_updater_prompt = PromptTemplate.from_template(search_queries_updater_template)
hs_answer_generator_system_msg = """\
You are an advanced assistant in satisfying USER's information need. 

Input: you will be provided CONTENT and user's QUERY. Output: should be a full or partial (but still helpful!) answer to QUERY based on CONTENT. If CONTENT doesn't have needed info output should be "This content does not contain needed information.".

Examples 1:
<CONTENT>SOURCE: https://en.wikipedia.org/wiki/Python_(programming_language)

Python is an interpreted high-level general-purpose programming language. Python's design philosophy emphasizes code readability with its notable use of significant indentation. Its language constructs and object-oriented approach aim to help programmers write clear, logical code for small and large-scale projects.
</CONTENT>
<QUERY>python code for how to merge dictionaries</QUERY>

Output: This content does not contain needed information.

Examples 2:
<CONTENT>SOURCE: https://www.marketplace.org/2020/06/19

CNN is an American news-based pay television channel owned by AT&T's WarnerMedia. CNN was founded in 1980 by media proprietor Ted Turner as a 24-hour cable news channel. Upon its launch, CNN was the first television channel to provide 24-hour news coverage, and was the first all-news television channel in the United States.
</CONTENT>
<QUERY>Who was USSR's leader when cnn appeared</QUERY>

Output: According to this [marketplace.org article](https://www.marketplace.org/2020/06/19) from June 19, 2020, CNN was launched in 1980 by media proprietor Ted Turner. The leader of the USSR at that time was Leonid Brezhnev.

Examples 3:
<CONTENT>SOURCE: https://www.nationalgeographic.com/animals

The cheetah is the fastest land animal, capable of reaching speeds up to 75 mph in short bursts covering distances up to 500 meters, and has the ability to accelerate from 0 to 60 mph in just a few seconds.
</CONTENT>
<QUERY>What is the top speed of a cheetah?</QUERY>

Output: [The National Geographic](https://www.nationalgeographic.com/animals) states that the top speed of a cheetah is 75 mph. Cheetahs can reach this speed in short bursts covering distances up to 500 meters.

Examples 4:
<CONTENT>SOURCE: https://www.history.com/topics/ancient-rome/colosseum

The Colosseum, also known as the Flavian Amphitheatre, is an oval amphitheatre in the center of the city of Rome, Italy. Built of travertine limestone, tuff (volcanic rock), and brick-faced concrete, it was the largest amphitheatre ever built at the time and held 50,000 to 80,000 spectators.
</CONTENT>
<QUERY>What materials were used to build the Colosseum?</QUERY>

Output: As explained in [this article](https://www.history.com/topics/ancient-rome/colosseum), the Colosseum was built using travertine limestone, tuff (volcanic rock), and brick-faced concrete.

Example 5:
<CONTENT>SOURCE: https://docs.pydantic.dev/latest/concepts/unions

Unions are fundamentally different to all other types Pydantic validates - instead of requiring all fields/items/values to be valid, unions require only one member to be valid.
This leads to some nuance around how to validate unions:
which member(s) of the union should you validate data against, and in which order?
which errors to raise when validation fails?
Validating unions feels like adding another orthogonal dimension to the validation process.
<...rest of a long article about unions that doesn't contain information about using __init__ in pydantic>
</CONTENT>
<QUERY>tutorial or documentation showing proper use of __init__ in pydantic</QUERY>

Output: This content does not contain needed information.

Example 6:
<CONTENT>SOURCE: https://stackoverflow.com/questions/66652334
<beginning of thread about __init__ in pydantic>
4 Answers
Sorted by: Highest score (default) 9

Because you have overidden pydantic's init method that is executed when a class that inherits from BaseModel is created. you should call super()

def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.__exceptions = []
<...further discussion about __init__ in pydantic with examples and links to docs>
</CONTENT>
<QUERY>tutorial or documentation showing proper use of __init__ in pydantic</QUERY>

Output: This [Stack Overflow post](https://stackoverflow.com/questions/66652334) discusses the proper use of __init__ in Pydantic. It explains that when defining a Base model that inherits from Pydantic's BaseModel, you should call super().__init__(**kwargs) in the __init__ method to avoid errors. Additionally, it provides examples and links to Pydantic documentation for further reference.

Example 7:
<CONTENT>SOURCE: https://www.nytimes.com/2024/05/01/trump-hush-money-trial-transcript.html

The transcript of the trial on April 30, 2024, revealed that former President Donald Trump was involved in the hush money payments to Stormy Daniels. The trial also exposed the role of Michael Cohen in facilitating the payments and the subsequent cover-up. <...rest of article, which discusses the transcript further but doesn't provide the transcript itself or a link to it>
</CONTENT>
<QUERY>/re hs find transcript of trial involving Trump</QUERY>

Output: This content does not contain needed information.

Example 8:
<CONTENT>SOURCE: https://whitehouse.gov/2024/05/01/remarks.html

DR. JILL BIDEN: "Michelle Obama and I have been friends for many years. She is a wonderful person and a great friend. I am honored to have her support in my work as First Lady."
</CONTENT>
<QUERY>find a quote by president Biden about Michelle Obama</QUERY>

Output: This content does not contain needed information.
"""

hs_answer_generator_template = """\
<CONTENT>{context}</CONTENT>
<QUERY>{query}</QUERY>"""

hs_answer_generator_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", hs_answer_generator_system_msg),
        # MessagesPlaceholder(variable_name="chat_history"),
        ("user", hs_answer_generator_template),
    ]
)


answer_evaluator_template = """\
You are an expert at evaluating the quality of answers. Input: you will be provided with user's query and an LLM's answer. Output: should be one of the following:
1. Reply with just one word "EXCELLENT" - if the answer is perfectly relevant and complete
2. "GOOD" - if the answer provides important information clearly relevant to the query, but is not perfectly complete
3. "MEDIUM" - if the answer is somewhat relevant, but needs significant improvement
4. "BAD" - if the answer is irrelevant or unhelpful

Example 1:
<QUERY>What is the capital of France?</QUERY>
<ANSWER>The capital of France is Paris</ANSWER>

Output: EXCELLENT

Example 2:
<QUERY>find a quote by obama about jill biden</QUERY>
<ANSWER>According to [this source](https://time.com/4426150/dnc-barack-obama-transcript/), President Obama praised his wife, Michelle Obama, for her dedication to promoting education for girls and fighting for healthy lunches. There is no specific quote by Obama about Jill Biden in the provided content.</ANSWER>

Output: BAD

Example 3:
<QUERY>find a quote by obama about jill biden</QUERY>
<ANSWER>Barack Obama said that Jill Biden is a wonderful person and a great friend</ANSWER>

Output: MEDIUM
Explanation of output: somewhat relevant but lacks actual quote

Example 4:
<QUERY>find a quote by obama about jill biden</QUERY>
<ANSWER>According to [this source](https://www.cosmopolitan.com/entertainment/celebs/), Michelle Obama said, "Dr. Biden gives us a better example. And this is why I feel so strongly that we could not ask for a better First Lady. She will be a terrific role model not just for young girls but for all of us, wearing her accomplishments with grace, good humor, and, yes, pride."</ANSWER>

Output: MEDIUM
Explanation of output: "obama" generally refers to Barack Obama, not Michelle Obama

Example 5:
<QUERY>How do electric cars contribute to reducing pollution?</QUERY>
<ANSWER>According to [GreenTech Media](https://www.greentechmedia.com/electric-cars-reducing-pollution), electric cars reduce pollution by eliminating tailpipe emissions. The article notes that widespread adoption can significantly decrease urban air pollution.</ANSWER>

Output: GOOD
Explanation of output: This answer is relevant and but could be improved by addressing the production and disposal phases of electric cars to provide a more complete analysis.

Example 6:
<QUERY>tutorial or documentation showing proper use of __init__ in pydantic</QUERY>
<ANSWER>The provided content does not contain specific information about the proper use of __init__ in Pydantic. For detailed tutorials or documentation showing the proper use of __init__ in Pydantic, it would be best to refer directly to the official Pydantic documentation or specific tutorials related to Pydantic's __init__ method.</ANSWER>

Output: BAD
Explanation of output: The answer is unhelpful as it explicitly states that the content does not contain the information requested.

Example 7:
<QUERY>tutorial or documentation showing proper use of __init__ in pydantic</QUERY>
<ANSWER>This [Stack Overflow post](https://stackoverflow.com/questions/66652334) discusses the proper use of __init__ in Pydantic. It explains that when defining a Base model that inherits from Pydantic's BaseModel, you should call super().__init__(**kwargs) in the __init__ method to avoid errors. Additionally, it provides examples and links to Pydantic documentation for further reference.</ANSWER>

Output: EXCELLENT

Example 8:
<QUERY>What role do antioxidants play in human health?</QUERY>
<ANSWER>[HealthLine](https://www.healthline.com/nutrition/antioxidants-explained) explains that antioxidants help to neutralize free radicals in the body, which can prevent cellular damage and reduce the risk of certain chronic diseases. However, the article suggests that the impact of antioxidants might vary based on the source and type consumed. Specific examples of antioxidants include vitamins C and E, beta-carotene, and selenium. The article also notes that some studies have suggested that antioxidant supplements may not be as beneficial as consuming antioxidants through whole foods.</ANSWER>

Output: EXCELLENT

Actual prompt:
<QUERY>{query}</QUERY>
<ANSWER>{answer}</ANSWER>

Output: """
answer_evaluator_prompt = PromptTemplate.from_template(answer_evaluator_template)

## SAMPLE QUERIES
"""
/re hs find example code showing how to update React state in shadcn ui Slider component
/re hs find a quote by obama about jill biden
/re hs 2 tutorial or documentation showing proper use of __init__ in pydantic
/re hs search the web specifically for "llms wearing pants" and tell me what it means
example code in python how to stream response from openai api.
[NOTE: ChatGPT and Gemini Advanced give bad answers to the above query.]
"""

evaluation_code_to_grade = {
    "EXCELLENT": "A",
    "GOOD": "B",
    "MEDIUM": "C",
    "BAD": "D",
    None: "?",
}


def shorten_url(url: str) -> str:
    parts = url.split("://")[-1].split("/")
    if len(parts) > 1:
        return parts[0] + "/..."
    return parts[0] if parts else url


class HeatseekData(BaseModel):
    query: str
    search_queries: list[str]
    past_search_queries: list[str] = Field(default_factory=list)
    url_conveyer: URLConveyer
    doc_conveyer: DocConveyer
    is_answer_found: bool = False
    answers: list[str] = Field(default_factory=list)
    evaluations: list[str] = Field(default_factory=list)


MIN_OK_URLS = 5
INIT_BATCH_SIZE = 8
MAX_SUB_ITERATIONS_IN_ONE_GO = 12  # can only reach if some sites are big and get split
MAX_URL_RETRIEVALS_IN_ONE_GO = 1

NUM_URLS_BEFORE_REFRESH = 70
NUM_LEFT_URLS_FOR_REFRESH = 12

CHECKED_STR = "I checked but didn't find a good answer in "
answer_found_evaluations = ["EXCELLENT"]
content_insufficient_evaluations = ["BAD"]
evaluations_to_record_answers = ["EXCELLENT", "GOOD", "MEDIUM"]


def run_main_heatseek_workflow(
    chat_state: ChatState, hs_data: HeatseekData, init_reply=""
):
    if full_reply := init_reply:
        chat_state.add_to_output(full_reply)

    # Process URLs one by one (unless content is too big, then split it up)
    new_checked_block = True
    source = "SOME RANDOM STRING TO THEN INITIALIZE prev_source"
    init_num_url_retrievals = hs_data.url_conveyer.num_url_retrievals
    for _ in range(MAX_SUB_ITERATIONS_IN_ONE_GO):
        # Get next batch of URLs if needed
        if hs_data.doc_conveyer.num_available_docs == 0:
            if (
                hs_data.url_conveyer.num_url_retrievals - init_num_url_retrievals
                >= MAX_URL_RETRIEVALS_IN_ONE_GO
            ):
                logger.info("Reached max number of URL retrievals")
                break
            logger.info("Getting next batch of URL content")
            docs = hs_data.url_conveyer.get_next_docs_with_url_retrieval()
            hs_data.doc_conveyer.add_docs(docs)

        # Get a batch of docs (in heatseek,
        # we only get one full doc at a time, but if it's big, it can come in parts)
        docs = hs_data.doc_conveyer.get_next_docs(
            max_tokens=CONTEXT_LENGTH * 0.5, max_full_docs=1
        )
        if not docs:
            logger.warning("No docs available")
            break  # unlikely to happen, but just in case

        prev_source = source
        source = docs[0].metadata["source"]
        logger.info(
            f"Getting response from LLM for source: {source} "
            f"(values of part_id: {[doc.metadata.get('part_id') for doc in docs]}"
        )

        # Construct the context and get response from LLM
        context = f"SOURCE: {source}\n\n{''.join(doc.page_content for doc in docs)}"
        logger.debug(f"Context:\n{DELIMITER40}{context}\n{DELIMITER40}")

        inputs = {"query": hs_data.query, "context": context}
        reply = chat_state.get_llm_reply(
            hs_answer_generator_prompt, inputs, to_user=False
        )
        logger.debug(f"LLM reply: {reply}")

        # Check if content is insufficient (this can change from False to True if
        # the evaluator gives a bad evaluation later on)
        is_content_insufficient = "content does not contain needed information" in reply

        # Parse response
        if not is_content_insufficient:
            # If LLM wrote a reply, evaluate it first
            inputs = {"query": hs_data.query, "answer": reply}
            logger.info("Getting response from evaluator")
            evaluator_reply = chat_state.get_llm_reply(
                answer_evaluator_prompt, inputs, to_user=False
            )

            # Parse evaluator response and decide whether to continue
            evaluation = has_which_substring(
                evaluator_reply, ["EXCELLENT", "GOOD", "MEDIUM", "BAD"]
            )
            logger.info(f"Evaluation: {evaluation}")

            is_content_insufficient = evaluation in content_insufficient_evaluations

            if not is_content_insufficient:
                # If LLM omitted the source, add it
                if source not in reply:
                    reply += f"\n\nSource: {source}"

                # Add to the full reply
                piece = ("\n\n" if full_reply else "") + reply
                piece += f"\n\nEVALUATION: {evaluation_code_to_grade[evaluation]}"
                full_reply += piece
                chat_state.add_to_output(piece)
                hs_data.is_answer_found = evaluation in answer_found_evaluations
                new_checked_block = True

            # Record answer and evaluation if needed
            if evaluation in evaluations_to_record_answers:
                hs_data.answers.append(reply)
                hs_data.evaluations.append(evaluation)

            # If answer is found, break
            if hs_data.is_answer_found:
                break

        if is_content_insufficient:
            # If content is insufficient, add to the "Checked: " block
            logger.info("Content is insufficient")
            logger.debug(f"{source=}, {prev_source=}, {new_checked_block=}")
            if source != prev_source:
                if new_checked_block:
                    piece = f"\n\n{CHECKED_STR}" if full_reply else CHECKED_STR
                    new_checked_block = False
                else:
                    piece = ", "
                piece += f"[{shorten_url(source)}]({source})"
                full_reply += piece
                chat_state.add_to_output(piece)

    # Add final piece if needed
    piece = ""
    if full_reply == init_reply:  # just in case
        logger.warning("Shouldn't happen: full_reply == init_reply")
        if init_reply:
            piece = "\n\n"
        piece += "I checked but didn't find a good answer on this round."

    if chat_state.parsed_query.research_params.num_iterations_left < 2:
        piece += (
            "\n\nTo continue checking more sources, type "
            "`/research heatseek <number of iterations to auto-run>`. For example, try "
            "`/re hs 4` (shorthand is ok)."
        )

    if piece:
        full_reply += piece
        chat_state.add_to_output(piece)

    return full_reply


def _update_search_queries(hs_data: HeatseekData, queries: list[str]):
    hs_data.past_search_queries.extend(hs_data.search_queries)
    hs_data.search_queries = queries

    # Get new URLs
    urls = get_links_from_queries(queries, num_search_results=100)
    hs_data.url_conveyer.refresh_urls(urls)
    logger.info(f"Refreshed URLs with {len(urls)} new URLs")
    logger.debug(f"New URLs: {urls}")


MAX_PREV_ANSWERS = 10
MAX_TOT_CHARS_IN_PREV_ANSWERS = 10000


class AnalysisAndQueries(BaseModel):
    analysis: str
    queries: list[str]


def auto_update_search_queries(hs_data: HeatseekData, chat_state: ChatState):
    # Get previous answers and evaluations
    answers_and_evals = []
    num_chars_tot = 0  # don't want to spend cpu to count tokens
    for answer, evaluation in zip(
        hs_data.answers[: -MAX_PREV_ANSWERS - 1 : -1],
        hs_data.evaluations[: -MAX_PREV_ANSWERS - 1 : -1],
    ):
        tmp = f"ANSWER (evaluation - {evaluation}): {answer}"
        num_chars_tot += len(tmp)
        if num_chars_tot > MAX_TOT_CHARS_IN_PREV_ANSWERS:
            # Make sure we have at least one answer and break
            if not answers_and_evals:
                answers_and_evals.append(tmp[:MAX_TOT_CHARS_IN_PREV_ANSWERS] + "...")
            break
        answers_and_evals.append(tmp)

    # Assemble answers and evaluations in chronological order
    past_answers = "\n\n".join(reversed(answers_and_evals))

    # Get new search queries
    query_updater_chain = chat_state.get_prompt_llm_chain(
        hs_query_updater_prompt, to_user=False
    )
    analysis_and_queries: AnalysisAndQueries = enforce_pydantic_json(
        query_updater_chain,
        inputs={
            "query": hs_data.query,
            "timestamp": get_timestamp(),
            "past_answers": past_answers,
            "past_search_queries": str(  # first 50 past search queries + latest
                hs_data.past_search_queries[:50] + hs_data.search_queries
            ),
        },
        pydantic_model=AnalysisAndQueries,
    )
    logger.info(f"Analysis and new search queries: {analysis_and_queries}")
    _update_search_queries(hs_data, analysis_and_queries.queries)
    return analysis_and_queries


def get_new_heatseek_response(chat_state: ChatState) -> JSONishDict:
    query = chat_state.message

    # Get links from prompt
    queries = get_web_search_queries_from_prompt(
        hs_query_generator_prompt,
        inputs={"query": query, "timestamp": get_timestamp()},
        chat_state=chat_state,
    )
    urls = get_links_from_queries(queries, num_search_results=100)
    # if not links:
    #     return {"early_exit_msg": WEB_SEARCH_API_ISSUE_MSG}

    # Initialize URLConveyer and DocConveyer
    url_conveyer = URLConveyer(
        urls=urls,
        default_min_ok_urls=MIN_OK_URLS,
        default_init_batch_size=INIT_BATCH_SIZE,
    )
    doc_conveyer = DocConveyer(max_tokens_for_breaking_up_docs=CONTEXT_LENGTH * 0.25)

    # Initialize HeatseekData - representing the state of the heatseek agent
    hs_data = HeatseekData(
        query=query,
        search_queries=queries,
        url_conveyer=url_conveyer,
        doc_conveyer=doc_conveyer,
    )

    # Perform main Heatseek workflow
    full_reply = run_main_heatseek_workflow(chat_state, hs_data)

    # Save agent state into ChromaDB
    vectorstore = ingest_into_collection(
        docs=[],
        collection_name=construct_new_collection_name(query, chat_state),
        collection_metadata={
            "agent_data": json.dumps({"hs": hs_data.model_dump_json()})
        },
        chat_state=chat_state,
        is_new_collection=True,
        retry_with_random_name=True,
    )

    # Return response (next iteration info will be added upstream)
    return {"answer": full_reply, "vectorstore": vectorstore}


def get_heatseek_in_progress_response(
    chat_state: ChatState, hs_data: HeatseekData
) -> JSONishDict:
    # Check if search queries and URLs need to be updated
    if (
        hs_data.url_conveyer.num_tried_urls_since_refresh >= NUM_URLS_BEFORE_REFRESH
        or hs_data.url_conveyer.num_untried_urls <= NUM_LEFT_URLS_FOR_REFRESH
    ):
        analysis_and_queries = auto_update_search_queries(hs_data, chat_state)
        init_reply = (
            "I decided to update the web search queries.\n\n"
            f"**Analysis:** {analysis_and_queries.analysis}\n\n"
            f"**New search queries:** {str(analysis_and_queries.queries)[1:-1]}\n\n"
        )
    else:
        init_reply = ""

    # Perform main Heatseek workflow
    full_reply = run_main_heatseek_workflow(chat_state, hs_data, init_reply)

    # Save agent state into ChromaDB
    chat_state.save_agent_data(
        {"hs": hs_data.model_dump_json()},
        use_cached_metadata=True,
    )

    return {"answer": full_reply}


# NOTE: should catch and handle exceptions in main handler
def get_research_heatseek_response(chat_state: ChatState) -> Props:
    if chat_state.message:
        return get_new_heatseek_response(chat_state)

    hs_data = chat_state.get_agent_data(use_cached_metadata=True).get("hs")
    # NOTE: We are using use_cached_metadata=True because metadata was fetched in the
    # call to get_rr_data in the get_research_response function
    if hs_data:
        hs_data = HeatseekData.model_validate_json(hs_data)
        return get_heatseek_in_progress_response(chat_state, hs_data)

    return format_nonstreaming_answer(
        "To start a new heatseek, type `/re heatseek <your query>`. I will then "
        "keep searching the web and going through the results until I find a satisfactory answer."
    )
