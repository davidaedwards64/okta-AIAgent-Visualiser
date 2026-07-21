import { apiRequest } from "./client";

export interface MeResponse {
  connected: boolean;
  org_domain?: string | null;
}

export interface LoginRequest {
  org_domain: string;
  client_id: string;
  client_secret?: string;
}

export interface LoginResponse {
  authorize_url: string;
}

export function getMe(): Promise<MeResponse> {
  return apiRequest<MeResponse>("/auth/me");
}

export function login(body: LoginRequest): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function logout(): Promise<{ ok: boolean }> {
  return apiRequest<{ ok: boolean }>("/auth/logout", { method: "POST" });
}
