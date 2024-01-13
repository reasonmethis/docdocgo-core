from pydantic import BaseModel, Field

from utils.web import LinkData


class Report(BaseModel):
    report: str
    sources: list[str]
    evaluation: str | None


class ResearchReportData(BaseModel):
    query: str
    generated_queries: list[str]
    report_type: str
    unprocessed_links: list[str]
    processed_links: list[str]
    link_data_dict: dict[str, LinkData]
    max_tokens_final_context: int
    report: str = ""
    preliminary_reports: list[Report] = Field(default_factory=list)
    num_obtained_unprocessed_links: int = 0
    num_obtained_unprocessed_ok_links: int = 0
    evaluation: str | None = None
    collection_name: str | None = None  # TODO: remove this
