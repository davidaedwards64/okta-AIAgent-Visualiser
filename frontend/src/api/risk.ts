import { apiRequest } from "./client";
import type { RiskReportResponse } from "../types/risk";

export function getRiskReport(): Promise<RiskReportResponse> {
  return apiRequest<RiskReportResponse>("/api/risk-report");
}
