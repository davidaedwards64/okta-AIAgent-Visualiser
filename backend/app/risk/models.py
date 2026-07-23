from typing import Literal

from pydantic import BaseModel


class RiskFinding(BaseModel):
    rule_id: str
    rule_name: str
    level: Literal["LOW", "MEDIUM", "HIGH"]
    description: str
    agent_id: str
    agent_name: str
    detail: str


class RiskReportResponse(BaseModel):
    generated_at: str
    org_domain: str
    findings: list[RiskFinding]
    warnings: list[str] = []
