from langchain_core.prompts import PromptTemplate

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

just_chat_template = """You are DocDocGo, a friendly Assistant AI who has been equipped with your own special knowledge base and the ability to do Internet research. For this particular reply you won't be retrieving any information from your knowledge base or the Internet. Instead, you will just chat with the user, keeping in mind that you may have used your knowledge base and/or the Internet earlier in the conversation.

CURRENT CHAT HISTORY:
{chat_history}
Human: {message}
AI: """
JUST_CHAT_PROMPT = PromptTemplate.from_template(just_chat_template)

qa_template_chat = """You are DocDocGo, a helpful Assistant AI who has been equipped with your own special knowledge base. In response to the user's query you have retrieved the most relevant parts of your knowledge base you could find:

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

simple_researcher_template = """You are an expert at converting raw google search results that come in a JSON format into a nicely formatted human-friendly response. 

RAW GOOGLE SEARCH RESULTS:

{results}

USER SEARCHED FOR: {query}

YOUR RESPONSE: """
SIMPLE_RESEARCHER_PROMPT = PromptTemplate.from_template(simple_researcher_template)

researcher_template0 = """You are a friendly Assistant AI who has been equipped with the tool to search the web. In response to the user's query you have conducted web searches and retrieved these results:

{texts_str}

END OF RETRIEVED INFO

USER'S QUERY: {query}

YOUR TASK: throw out irrelevant info and write a LONG well-crafted, well-formatted report to help the user and present the info in a digestible way.

YOUR RESPONSE: """

researcher_template_gpt_researcher = (
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

researcher_template_short_and_sweet = """<sources>{texts_str}</sources>
Please extract all information relevant to the following query: 
<query>{query}</query>
Write a report, which should be: 1500-2000 words long, in markdown syntax, in apa format. List the references used.
"""
RESEARCHER_PROMPT_SIMPLE = PromptTemplate.from_template(
    researcher_template_short_and_sweet
)

researcher_template_dynamic_report = """<sources>{texts_str}</sources>
Please extract all information relevant to the following query: 
<query>{query}</query>
Write a report in Markdown syntax, which should be: {report_type}. List the references used, with URLs if available.
"""
RESEARCHER_PROMPT_DYNAMIC_REPORT = PromptTemplate.from_template(
    researcher_template_dynamic_report
)

summarizer_template = """<source>{text}</source>
Given the following query:
<query>{query}</query>
please remove any sections that are completely off-topic to the query. Keep the rest as is.

# Guidelines for what counts as off-topic

Cookie consent messages, ads, and other boilerplate text are off-topic.
If a section addresses a completely different domain, it is off-topic. Example: query is "atomic physics", but an article is about dog grooming (and it's not used to illustrate a concept in atomic physics).

# Guidelines for what counts as on-topic

A section doesn't have to directly answer the query to be kept: if it is in the same general ballpark or on a related topic, that's good enough.

# Output
Your entire output should be the original text sans off-topic sections."""

summarizer_template = """ORIGINAL TEXT:
{text}

END OF ORIGINAL TEXT
Please reproduce the original text as is with only the following modification:
- Keep only sections that may in some, even indirect way, be related to the following query: 
{query}

Your output should be just the modified text, no other info.
"""
SUMMARIZER_PROMPT = PromptTemplate.from_template(summarizer_template)

query_generator_template = """# MISSION
You are an advanced assistant in satisfying USER's information need.

# INPUT 
You are given the following query: {query}
Current timestamp: {timestamp}

# HIGH LEVEL TASK
You don't need to answer the query. Instead, your goal is to determine the information need behind the query and help USER generate a sophisticated plan to satisfy that information need.

# OUTPUT
There are two parts to your output:

## PART 1: Array of google search queries that would be most helpful to perform. These could be sub-questions and/or different ways to rephrase the original query to get an objective, unbiased, up-to-date answer. Use everything you know about information foraging and information literacy in this task.

## PART 2: Brief description of the type of answer/report that will best suit the information need. Examples: "comprehensive report in apa format", "step by step plan of action", "brief one sentence answer", "python code snippet", etc. Use your best judgement to describe the report that will best satisfy the information need. Keep in mind that the report will be written by another LLM, so it can't have images.

Your output should be in JSON following the examples below.

## EXAMPLES OF OUTPUT 

query: "How do I start with Langchain? I want to use it to make a chatbot that I can deploy on a website."
timestamp: Thursday, March 13, 2025, 04:40 PM

output: {{"queries": ["langchain chatbot tutorial March 2025", "langchain getting started", "deploy langchain chatbot on website"],
"report_type": "step by step guide including code snippets, 1500-3000 words"}}


query: "openai news"
timestamp: Saturday, June 22, 2024, 11:01 AM

output: {{"queries": ["openai news June 22 2024", "openai products new features June 2024", "openai organization updates June 2024"],
"report_type": "specifics-dense report rich in facts and figures, 1000-2000 words long"}}


query: "how can I merge two dictionaries in python?"
timestamp: Saturday, November 08, 2025, 06:04 PM

output: {{"queries": ["python merge dictionaries", "python 2025 dictionary union"],
"report_type": "python code snippet with explanation, likely less than 500 words"}}


query: "could you give me a comprehensive medical report on treating chronic migraines?"
timestamp: Monday, August 12, 2024, 11:15 PM

output: {{"queries": ["chronic migraines treatment", "medications for chronic migraines", "non-drug treatments for chronic migraines", "differential diagnosis migraines", "alternative treatments for chronic migraines", "chronic migraines recent research August 2024"],
"report_type": "comprehensive medical report, 1500-2000 words long"}}


query: "how old was John Lennon during the Cuban Missile Crisis?"
timestamp: Tuesday, September 12, 2023, 07:39 AM

output: {{"queries": ["John Lennon birth date", "Cuban Missile Crisis dates"],
"report_type": "brief relevant facts, followed by a formula to calculate the answer, followed by the answer"}}


query: "how old was John Lennon during the Cuban Missile Crisis? I want a report in apa format."
timestamp: Tuesday, September 12, 2023, 07:39 AM

output: {{"queries": ["John Lennon birth date", "Cuban Missile Crisis dates", "John Lennon during Cuban Missile Crisis"],
"report_type": "report in apa format, around 1000 words long"}}

# YOUR ACTUAL OUTPUT
query: "{query}"
timestamp: {timestamp}

output: """
QUERY_GENERATOR_PROMPT = PromptTemplate.from_template(query_generator_template)

iterative_report_improver_template = """\
You are AIRIA, Advanced Iterative Report Improvement Assistant. 

USER's query: {query}

MISSION: improve the report you generated on your previous iteration, with the help of the following additional information you retrieved:

{new_info}

END OF NEW INFORMATION YOU RETRIEVED

Your previous iteration's report: 

{previous_report}

END OF PREVIOUS ITERATION'S REPORT

If the new information you retrieved is useful to improve the report to best serve USER's information need, please output the improved report, followed immediately by "REPORT ASSESSMENT: X%, where X is your estimate of how well the report serves USER's information need on a scale from 0% to 100%, based on their query: 

{query}

If the new information isn't useful to improve previous report then don't output a report, simply output "NO IMPROVEMENT, PREVIOUS REPORT ASSESSMENT: X%", where X is your estimate of how well the previous report serves USER's information need. Output: """

ITERATIVE_REPORT_IMPROVER_PROMPT = PromptTemplate.from_template(
    iterative_report_improver_template
)
