import { apiRequest } from "./client";
import type { GraphResponse } from "../types/graph";

export function getGraph(): Promise<GraphResponse> {
  return apiRequest<GraphResponse>("/api/graph");
}

// Same data as getGraph(), but over Server-Sent Events so the caller can
// show real progress ("Fetching AI Agents...", "Resolving groups...", ...)
// instead of one static loading message for the whole request.
export function streamGraph(onProgress: (message: string) => void): Promise<GraphResponse> {
  return new Promise((resolve, reject) => {
    const source = new EventSource("/api/graph/stream", { withCredentials: true });

    source.onmessage = (evt) => {
      const payload = JSON.parse(evt.data) as { stage: string; message?: string; graph?: GraphResponse };
      if (payload.stage === "done" && payload.graph) {
        source.close();
        resolve(payload.graph);
      } else if (payload.stage === "error") {
        source.close();
        reject(new Error(payload.message || "Failed to load graph"));
      } else if (payload.message) {
        onProgress(payload.message);
      }
    };

    source.onerror = () => {
      source.close();
      reject(new Error("Failed to load graph"));
    };
  });
}

export interface GroupMemberSummary {
  id: string;
  label: string;
  status?: string | null;
  sub_label?: string | null;
}

export interface GroupMembersResponse {
  group_id: string;
  members: GroupMemberSummary[];
  total_count: number;
}

export function getGroupMembers(groupOktaId: string): Promise<GroupMembersResponse> {
  return apiRequest<GroupMembersResponse>(`/api/groups/${encodeURIComponent(groupOktaId)}/members`);
}
