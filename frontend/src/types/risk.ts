// Mirrors backend/app/risk/models.py by hand — keep in sync.

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export interface RiskFinding {
  rule_id: string;
  rule_name: string;
  level: RiskLevel;
  description: string;
  agent_id: string;
  agent_name: string;
  detail: string;
}

export interface RiskReportResponse {
  generated_at: string;
  org_domain: string;
  findings: RiskFinding[];
  warnings: string[];
}
