import json
from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from langchain.schema.output_parser import StrOutputParser

from utils.prompts import WEBSEARCHER_PROMPT
from components.llm import get_llm

search = GoogleSerperAPIWrapper()


def get_websearcher_response(message: str):
    search_results = search.results(message)
    json_results = json.dumps(search_results, indent=4)

    chain = WEBSEARCHER_PROMPT | get_llm(print_streamed=True) | StrOutputParser()
    answer = chain.invoke({"results": json_results, "query": message})
    return {"answer": answer}
