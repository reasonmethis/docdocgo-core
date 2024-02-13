from pydantic import BaseModel, Field, model_validator

from utils.web import LinkData


class Report(BaseModel):
    report_text: str
    sources: list[str] = Field(default_factory=list)
    parent_report_ids: list[str] = Field(default_factory=list)
    child_report_id: str | None = None
    evaluation: str | None = None


class ResearchReportData(BaseModel):
    query: str
    search_queries: list[str]
    report_type: str
    unprocessed_links: list[str]
    processed_links: list[str]
    link_data_dict: dict[str, LinkData]
    max_tokens_final_context: int
    main_report: str = ""
    base_reports: list[Report] = Field(default_factory=list)
    combined_reports: list[Report] = Field(default_factory=list)
    combined_report_id_levels: list[list[str]] = Field(default_factory=list)  # levels
    num_obtained_unprocessed_links: int = 0
    num_obtained_unprocessed_ok_links: int = 0
    num_links_from_latest_queries: int | None = None
    evaluation: str | None = None
    collection_name: str | None = None  # TODO: remove this

    @model_validator(mode="after")
    def validate(self):
        if self.num_links_from_latest_queries is None:
            self.num_links_from_latest_queries = len(self.unprocessed_links)
        return self

    @property
    def num_processed_links_from_latest_queries(self) -> int:
        # All unprocessed links are from the latest queries so we just subtract
        return self.num_links_from_latest_queries - len(self.unprocessed_links)

    def is_base_report(self, id: str) -> bool:
        return not id.startswith("c")

    def is_report_childless(self, id: str) -> bool:
        return self.get_report_by_id(id).child_report_id is None

    def get_report_by_id(self, id) -> Report:
        return (
            self.base_reports[int(id)]
            if self.is_base_report(id)
            else self.combined_reports[int(id[1:])]
        )

    def get_parent_reports(self, report: Report) -> list[Report]:
        return [
            self.get_report_by_id(parent_id) for parent_id in report.parent_report_ids
        ]

    def get_ancestor_ids(self, report: Report) -> list[int]:
        res = []
        for parent_id in report.parent_report_ids:
            if self.is_base_report(parent_id):
                res.append(parent_id)
            else:
                res.extend(self.get_ancestor_ids(self.get_report_by_id(parent_id)))

    def get_sources(self, report: Report) -> list[str]:
        res = report.sources.copy()
        for parent_report in self.get_parent_reports(report):
            res.extend(self.get_sources(parent_report))
        return res
