from pydantic import BaseModel

from utils.web import LinkData


class WebsearcherData(BaseModel):
    query: str
    generated_queries: list[str]
    report: str = "NOT YET GENERATED"
    report_type: str
    unprocessed_links: list[str]
    processed_links: list[str]
    link_data_dict: dict[str, LinkData]
    num_obtained_unprocessed_links: int = 0
    num_obtained_unprocessed_ok_links: int = 0
    evaluation: str | None = None
    collection_name: str | None = None  # TODO: remove this
    max_tokens_final_context: int  #  = int(CONTEXT_LENGTH * 0.7)
