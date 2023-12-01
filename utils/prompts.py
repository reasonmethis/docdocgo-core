from langchain.prompts.prompt import PromptTemplate

condense_question_template = """Given the following chat history (between Human and you, the Assistant) add context to the last Query from Human so that it can be understood without needing to read the whole conversation: include necessary details from the conversation to make Query completely standalone:
1. First put the original Query as is or very slightly modified (e.g. replacing "she" with who this refers to) 
2. Then, add "[For context: <condensed summary to yourself of the relevant parts of the chat history: if Human asks a question and the answer is clear from the chat history, include it in the summary>]"

Examples of possible Standalone Queries:
- "And then? [For context: Human wrote this in response to your summary of the Big Bang. The general conversation was about the history of the universe.]"
- "How do you know this? [For context: you just summarized relevant parts of your knowledge base answering Human's question about installing Langchain. Briefly, you explained that they need to run "pip install langchain" and likely other libraries like openai, tiktoken, etc.]"
- "hm [For context: Human asked you to write a poem about Washington and you wrote one.]"
- "What was my first message to you? [For context: Human's first message in our chat history was <exact first message from Human in chat history, verbatim>.]

Chat History:
{chat_history}
Last Query from Human: {question}
Standalone version of Last Query: """
CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(condense_question_template)

qa_template_chat = """You are a helpful Assistant AI who has been equipped with your own special knowledge base. In response to the user's query you have retrieved the most relevant parts of your knowledge base you could find:

{context}

END OF PARTS OF YOUR KNOWLEDGE BASE YOU RETRIEVED.
Use them for your response ONLY if relevant.

CURRENT CHAT HISTORY:
{chat_history}
Human: {question}
AI: """

QA_PROMPT_CHAT = PromptTemplate.from_template(qa_template_chat)

qa_template_summarize_kb = """You are a helpful Assistant AI who has been equipped with your own special knowledge base. In response to the user's query you have retrieved the most relevant parts of your knowledge base you could find:

{context}

END OF RETRIEVED PARTS OF YOUR KNOWLEDGE BASE.

USER'S QUERY: {question}

YOUR TASK: present the retrieved parts in a digestible way:
1. Start with "<b>TLDR</b>" followed by a quick summary of only the retrieved parts directly relevant to the user's query, if there are any.
2. The full presentation must have section headings in bold. For this part, completely ignore user's query.

YOUR RESPONSE: """
QA_PROMPT_SUMMARIZE_KB = PromptTemplate.from_template(qa_template_summarize_kb)

qa_template_quotes = """You are a helpful Assistant AI who has been equipped with your own special knowledge base. In response to the user's query you have retrieved the most relevant parts of your knowledge base you could find:

{context}

END OF PARTS OF YOUR KNOWLEDGE BASE YOU RETRIEVED.

USER'S QUERY: {question}

YOUR TASK: print any quotes from your knowledge base relevant to user's query, if there are any.
YOUR RESPONSE: """
QA_PROMPT_QUOTES = PromptTemplate.from_template(qa_template_quotes)

simple_websearcher_template = """You are an expert at converting raw google search results that come in a JSON format into a nicely formatted human-friendly response. 

RAW GOOGLE SEARCH RESULTS:

{results}

USER SEARCHED FOR: {query}

YOUR RESPONSE: """
SIMPLE_WEBSEARCHER_PROMPT = PromptTemplate.from_template(simple_websearcher_template)

websearcher_template0 = """You are a friendly Assistant AI who has been equipped with the tool to search the web. In response to the user's query you have conducted web searches and retrieved these results:

{texts_str}

END OF RETRIEVED INFO

USER'S QUERY: {query}

YOUR TASK: throw out irrelevant info and write a LONG well-crafted, well-formatted report to help the user and present the info in a digestible way.

YOUR RESPONSE: """

websearcher_template_gpt_researcher = (
    'Information: """{texts_str}"""\n\n'
    "Using the above information, answer the following"
    ' query or task: "{query}" in a detailed report --'
    " The report should focus on the answer to the query, should be well structured, informative,"
    " in depth and comprehensive, with facts and numbers if available and a minimum of 1000 words.\n"
    "You should strive to write the report as long as you can using all relevant and necessary information provided.\n"
    "You must write the report with markdown syntax.\n "
    "Use an unbiased and journalistic tone. \n"
    "You MUST determine your own concrete and valid opinion based on the given information. Do NOT deter to general and meaningless conclusions.\n"
    "You MUST write all used source urls at the end of the report as references, and make sure to not add duplicated sources, but only one reference for each.\n"
    "You MUST write the report in apa format.\n "
    "Cite search results using inline notations. Only cite the most \
            relevant results that answer the query accurately. Place these citations at the end \
            of the sentence or paragraph that reference them.\n"
    "Please do your best, this is very important to my career. "
    "Assume that the current date is {datetime}"
)

websearcher_template_short_and_sweet = """<sources>{texts_str}</sources>
Please extract all information relevant to the following query: 
<query>{query}</query>
Write a report, which should be: 1500-2000 words long, in markdown syntax, in apa format. List the references used.
"""
WEBSEARCHER_PROMPT = PromptTemplate.from_template(websearcher_template_short_and_sweet)

websearcher_template_dynamic_report = """<sources>{texts_str}</sources>
Please extract all information relevant to the following query: 
<query>{query}</query>
Write a report in Markdown syntax, which should be: {report_type}. List the references used, with URLs if available.
"""
WEBSEARCHER_PROMPT_DYNAMIC_REPORT = PromptTemplate.from_template(
    websearcher_template_dynamic_report
)

summarizer_template = """<source>{text}</source>
Please write a summary of all information from the above source relevant to the following query:
<query>{query}</query>"""
SUMMARIZER_PROMPT = PromptTemplate.from_template(summarizer_template)

query_generator_template = """# MISSION
You are an advanced assistant in satisfying USER's information need.

# INPUT 
You are given a query: {query}

# HIGH LEVEL TASK
You don't need to answer the query. Instead, your goal is to determine the information need behind the query and help USER generate a sophisticated plan to satisfy that information need.

# OUTPUT
There are two parts to your output:

## PART 1: Array of google search queries that would be most helpful to perform. These could be sub-questions and/or different ways to rephrase the original query to get an objective, unbiased, up-to-date answer. Use everything you know about information foraging and information literacy in this task.

## PART 2: Brief description of the type of answer/report that will best suit the information need. Examples: "comprehensive report in apa format", "step by step plan of action", "brief one sentence answer", "python code snippet", etc. Use your best judgement to describe the report that will best satisfy the information need. Keep in mind that the report will be written by another LLM, so it can't have images.

Your output should be in JSON following the examples below.

## EXAMPLES OF OUTPUT 

query: "How do I start with Langchain? I want to use it to make a chatbot that I can deploy on a website."
output: {{"queries": ["langchain chatbot tutorial", "langchain getting started", "deploy langchain chatbot on website"],
"report_type": "step by step guide including code snippets, 1500-3000 words"}}

query: "openai news"
output: {{"queries": ["openai news", "openai products new features", "openai organization news"],
"report_type": "comprehensive report in apa format, 1000-2000 words long"}}

query: "how can I merge two dictionaries in python?"
output: {{"queries": ["python merge dictionaries", "python dictionary union"],
"report_type": "python code snippet with explanation, likely less than 500 words"}}

query: "treat chronic migraines"
output: {{"queries": ["chronic migraines treatment", "medications for chronic migraines", "non-drug treatments for chronic migraines", "differential diagnosis migraines", "alternative treatments for chronic migraines"],
"report_type": "comprehensive medical report, 1500-2000 words long"}}

query: "how old was John Lennon during the Cuban Missile Crisis?"
output: {{"queries": ["John Lennon birth date", "Cuban Missile Crisis dates"],
"report_type": "brief relevant facts, followed by a formula to calculate the answer, followed by the answer"}}

# YOUR ACTUAL OUTPUT
query: "{query}"
output: """
QUERY_GENERATOR_PROMPT = PromptTemplate.from_template(query_generator_template)

if __name__ == "__main__":
    # Here we can test the prompts
    # NOTE: Run this file as "python -m utils.prompts"

    from components.llm import get_llm_with_str_output_parser
    from utils.test_content import query_to_context
    from datetime import datetime
    import sys

    prompts_templates_to_test = [
        websearcher_template_gpt_researcher.replace(
            "{datetime}", datetime.now().strftime("%B %d, %Y")
        )
    ]

    query = "openai news"
    NUM_ITERATIONS = 2
    for iteration in range(NUM_ITERATIONS):
        print("\n" + "-" * 50)
        print("Iteration", iteration)
        print("-" * 50)
        for i, t in enumerate(prompts_templates_to_test):
            prompt = PromptTemplate.from_template(t)
            chain = prompt | get_llm_with_str_output_parser(
                temperature=0.2, print_streamed=True
            )
            print("Prompt", i)
            try:
                chain.invoke({"query": query, "texts_str": query_to_context[query]})
            except Exception as e:
                print("ERROR:", e)
