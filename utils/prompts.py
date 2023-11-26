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

YOUR TASK: present the info in a digestible way:
1. Start your report with TLDR section directly relevant to the user's query.
2. Then write a LONG report detailing all the information, broken into sections. For this part, completely ignore user's query. Don't call this part "Report".

YOUR RESPONSE: """

websearcher_template = """You are a friendly Assistant AI who has been equipped with the tool to search the web. In response to the user's query you have conducted web searches and retrieved these results:

{texts_str}

END OF RETRIEVED INFO

USER'S QUERY: {query}

YOUR TASK: throw out irrelevant info and write a LONG well-crafted, well-formatted report to help the user and present the info in a digestible way.

YOUR RESPONSE: """
WEBSEARCHER_PROMPT = PromptTemplate.from_template(websearcher_template)

if __name__ == "__main__":
    # Here we can test the prompts
    # NOTE: Run this file as "python -m utils.prompts"
 
    from components.llm import get_llm_with_output_parser
    from utils.test_content import query, content

    prompts_to_test = [WEBSEARCHER_PROMPT]

    for i, prompt in enumerate(prompts_to_test):
        chain = prompt | get_llm_with_output_parser(temperature=0, print_streamed=True)
        print("Prompt", i)
        chain.invoke({"query": query, "texts_str": content})
