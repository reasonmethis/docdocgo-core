from langchain.prompts import PromptTemplate
from pydantic import BaseModel

from agentblocks.collectionhelper import (
    get_collection_name_from_query,
    start_new_collection,
)
from agentblocks.docconveyer import DocConveyer, break_up_big_docs
from agentblocks.webprocess import URLConveyer
from agentblocks.webretrieve import get_content_from_urls
from agentblocks.websearch import get_web_search_result_urls_from_prompt
from utils.chat_state import ChatState
from utils.helpers import format_nonstreaming_answer, get_timestamp
from utils.prepare import CONTEXT_LENGTH, ddglogger
from utils.query_parsing import ParsedQuery
from utils.strings import has_which_substring
from utils.type_utils import JSONishDict

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

You will be provided information about USER's query and current state of formulating the answer. Your task is to determine what needs to be added or improved in order to better satisfy USER's information need and strategically design a list of google search queries that would be most helpful to perform.

# Input

1. USER's query: {query} 
END OF USER's query 

2. Current timestamp: {timestamp}
END OF timestamp

3. Requested answer format: {report_type}
END OF requested answer format

4. Google search queries used to generate the current draft of the answer: {search_queries}
END OF search queries

5. Current draft of the answer: {report}

# Detailed Task

Let's work step by step. First, you need to determine what needs to be added or improved in order to better satisfy USER's information need. Then, based on the results of your analysis, you need to strategically design a list of google search queries that would be most helpful to perform to get an accurate, complete, unbiased, up-to-date answer. Design these queries so that the google search results will provide the necessary information to fill in any gaps in the current draft of the answer, or improve it in any way.

Use everything you know about information foraging and information literacy in this task.

# Output

Your output should be in JSON in the following format:

{{"analysis": <brief description of what kind of information we should be looking for to improve the answer and why you think the previous google search queries may not have yielded that information>,
"queries": [<array of 3-7 new google search queries that would be most helpful to perform, based on that analysis>]}}

# Example

Suppose the user wants to get a numbered list of top Slavic desserts and you notice that the current draft includes desserts from Russia and Ukraine, but is missing desserts from other, non-former-USSR Slavic countries. You would then provide appropriate analysis and design new google search queries to fill in that gap, for example your output could be:

{{"analysis": "The current draft of the answer is missing desserts from other Slavic countries besides Russia and Ukraine. The current search queries seem to have resulted in content being mostly about countries from the former USSR so we should specifically target other Slavic countries.",
"queries": ["top desserts Poland", "top desserts Czech Republic", "top desserts Slovakia", "top desserts Bulgaria", "best desserts from former Yugoslavia", "desserts from Easern Europe"]}}

# Your actual output

Now, please use the information in the "# Input" section to construct your actual output, which should start with the opening curly brace and end with the closing curly brace:


"""
hs_query_updater_prompt = PromptTemplate.from_template(search_queries_updater_template)

hs_answer_generator_template = """\
You are an advanced assistant in satisfying USER's information need. Input: you will be provided CONTENT and user's QUERY. Output: should be one of the following:
1. Reply with a full, accurate, unbiased, up-to-date answer to QUERY - if CONTENT is sufficient to produce such an answer
OR
2. Just one word "CONTENT_INSUFFICIENT" - if CONTENT is insufficient to produce such an answer.

Examples 1:
<CONTENT>SOURCE: https://en.wikipedia.org/wiki/Python_(programming_language)

Python is an interpreted high-level general-purpose programming language. Python's design philosophy emphasizes code readability with its notable use of significant indentation. Its language constructs and object-oriented approach aim to help programmers write clear, logical code for small and large-scale projects.
</CONTENT>
<QUERY>python code for how to merge dictionaries</QUERY>

Output: CONTENT_INSUFFICIENT

Examples 2:
<CONTENT>SOURCE: https://www.marketplace.org/2020/06/19

CNN is an American news-based pay television channel owned by AT&T's WarnerMedia. CNN was founded in 1980 by media proprietor Ted Turner as a 24-hour cable news channel. Upon its launch, CNN was the first television channel to provide 24-hour news coverage, and was the first all-news television channel in the United States.
</CONTENT>
<QUERY>Who was USSR's leader when cnn appeared</QUERY>

Output: According to [this source](https://www.marketplace.org/2020/06/19), CNN was launched in 1980 by media proprietor Ted Turner. At that time, the leader of the USSR was Leonid Brezhnev. He led the Soviet Union from 1964 until his death in 1982. 

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

Actual prompt:
<CONTENT>{context}</CONTENT>
<QUERY>{query}</QUERY>

Output: """
hs_answer_generator_prompt = PromptTemplate.from_template(hs_answer_generator_template)

answer_evaluator_template = """\
You are an expert at evaluating the quality of answers. Input: you will be provided with user's query and an LLM's answer. Output: should be one of the following:
1. Reply with just one word "EXCELLENT" - if the answer is perfectly relevant and complete
2. "GOOD" - if the answer is mostly relevant and complete
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
Explanation of output: technically relevant but user almost certainly wanted a quote from Barack Obama, not just any Obama

Example 5:
<QUERY>How do electric cars contribute to reducing pollution?</QUERY>
<ANSWER>According to [GreenTech Media](https://www.greentechmedia.com/electric-cars-reducing-pollution), electric cars reduce pollution by eliminating tailpipe emissions. The article notes that widespread adoption can significantly decrease urban air pollution.</ANSWER>

Output: GOOD
Explanation of output: This answer is relevant and but could be improved by addressing the production and disposal phases of electric cars to provide a more complete analysis.

Example 6:
<QUERY>What role do antioxidants play in human health?</QUERY>
<ANSWER>[HealthLine](https://www.healthline.com/nutrition/antioxidants-explained) explains that antioxidants help to neutralize free radicals in the body, which can prevent cellular damage and reduce the risk of certain chronic diseases. However, the article suggests that the impact of antioxidants might vary based on the source and type consumed. Specific examples of antioxidants include vitamins C and E, beta-carotene, and selenium. The article also notes that some studies have suggested that antioxidant supplements may not be as beneficial as consuming antioxidants through whole foods.</ANSWER>

Output: EXCELLENT

Actual prompt:
<QUERY>{query}</QUERY>
<ANSWER>{answer}</ANSWER>

Output: """
answer_evaluator_prompt = PromptTemplate.from_template(answer_evaluator_template)

## SAMPLE QUERIES
# find example code showing how to update Ract state in shadcn ui Slider component
# find a quote by obama about jill biden

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
    url_conveyer: URLConveyer
    doc_conveyer: DocConveyer
    is_answer_found: bool
    answer: str


MIN_OK_URLS = 5
INIT_BATCH_SIZE = 8
MAX_SUB_ITERATIONS_IN_ONE_GO = 12  # can only reach if some sites are big and get split


def get_new_heatseek_response(chat_state: ChatState) -> JSONishDict:
    query = chat_state.message

    # Get links from prompt
    urls = get_web_search_result_urls_from_prompt(
        hs_query_generator_prompt,
        inputs={"query": query, "timestamp": get_timestamp()},
        num_links=100,
        chat_state=chat_state,
    )

    # Get content from links and initialize URLConveyer
    url_retrieval_data = get_content_from_urls(
        urls, min_ok_urls=MIN_OK_URLS, init_batch_size=INIT_BATCH_SIZE
    )
    url_conveyer = URLConveyer.from_retrieval_data(url_retrieval_data)

    # Convert retrieval data to docs and break up docs that are too big
    docs = url_conveyer.get_next_docs()
    docs = break_up_big_docs(docs, max_tokens=CONTEXT_LENGTH * 0.25)
    doc_conveyer = DocConveyer(docs=docs)

    full_reply = ""
    new_checked_block = True
    is_answer_found = False
    for _ in range(MAX_SUB_ITERATIONS_IN_ONE_GO):
        # Get a batch of docs (in heatseek,
        # we only get one full doc at a time, but if it's big, it can come in parts)
        docs = doc_conveyer.get_next_docs(
            max_tokens=CONTEXT_LENGTH * 0.5, max_full_docs=1
        )
        ddglogger.debug(
            f"Values for part_id of docs: {[doc.metadata.get('part_id') for doc in docs]}"
        )

        # If no more docs, break
        if not docs:
            full_reply = full_reply or "NO_CONTENT_FOUND"
            break

        # Construct the context and get response from LLM
        source = docs[0].metadata["source"]
        ddglogger.info(f"Getting response from LLM for user query from {source}")
        context = f"SOURCE: {source}\n\n{''.join(doc.page_content for doc in docs)}"
        inputs = {"query": query, "context": context}
        reply = chat_state.get_llm_reply(
            hs_answer_generator_prompt, inputs, to_user=False
        )

        # Parse response
        if "CONTENT_INSUFFICIENT" not in reply:
            # If LLM wrote a reply, add it to the full reply
            piece = ("\n\n" + reply) if full_reply else reply
            full_reply += piece
            chat_state.add_to_output(piece)

            # Get response from evaluator
            inputs = {"query": query, "answer": reply}
            ddglogger.info("Getting response from evaluator")
            evaluator_reply = chat_state.get_llm_reply(
                answer_evaluator_prompt, inputs, to_user=False
            )

            # Parse evaluator response and decide whether to continue
            evaluation = has_which_substring(
                evaluator_reply, ["EXCELLENT", "GOOD", "MEDIUM", "BAD"]
            )
            ddglogger.info(f"Evaluation: {evaluation}")
            piece = f"\n\nEVALUATION: {evaluation_code_to_grade[evaluation]}"
            full_reply += piece
            chat_state.add_to_output(piece)
            if is_answer_found := (evaluation in ["EXCELLENT", "GOOD"]):
                break
            new_checked_block = True
        else:
            # If content is insufficient, add to the "Checked: " block
            ddglogger.info("Content is insufficient")
            if new_checked_block:
                piece = "\n\nChecked: " if full_reply else "Checked: "
                new_checked_block = False
            else:
                piece = ", "
            piece += f"[{shorten_url(source)}]({source})"
            full_reply += piece
            chat_state.add_to_output(piece)

    if not is_answer_found:
        ddglogger.info("No satisfactory answer found")
        piece = "\n\nSo far, I have not found a source with a satisfactory answer."
        full_reply += piece
        chat_state.add_to_output(piece)

    # Construct data for future iterations
    hs_data_json = HeatseekData(
        query=query,
        url_conveyer=url_conveyer,
        doc_conveyer=doc_conveyer,
        is_answer_found=is_answer_found,
        answer=full_reply,
    ).model_dump_json()

    # Save agent state into ChromaDB
    vectorstore = start_new_collection(
        likely_coll_name=get_collection_name_from_query(query, chat_state),
        docs=[],
        collection_metadata={"agent_data": {"hs": hs_data_json}},
        chat_state=chat_state,
    )

    # Return response
    return {"answer": full_reply, "vectorstore": vectorstore}


def get_heatseek_in_progress_response(
    chat_state: ChatState, hs_data: JSONishDict
) -> JSONishDict:
    num_iterations = chat_state.parsed_query.research_params.num_iterations_left
    return format_nonstreaming_answer(
        f"NOT YET IMPLEMENTED: Your heatseek is in progress. {num_iterations} iterations left."
    )


# NOTE: should catch and handle exceptions in main handler
def get_research_heatseek_response(chat_state: ChatState) -> JSONishDict:
    if chat_state.message:
        return get_new_heatseek_response(chat_state)

    hs_data = chat_state.get_agent_data().get("hs_data")
    if hs_data:
        return get_heatseek_in_progress_response(chat_state, hs_data)

    return format_nonstreaming_answer(
        "To start a new heatseek, type `/re heatseek <your query>`. I will then "
        "keep searching the web and going through the results until I find a satisfactory answer."
    )
