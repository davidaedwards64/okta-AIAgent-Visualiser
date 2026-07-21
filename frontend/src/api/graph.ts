import { apiRequest } from "./client";
import type { GraphResponse } from "../types/graph";

export function getGraph(): Promise<GraphResponse> {
  return apiRequest<GraphResponse>("/api/graph");
}
