import { useState } from "react";
import { login } from "../api/auth";

function errorMessage(code: string | null): string | null {
  if (!code) return null;
  const messages: Record<string, string> = {
    no_session: "Your session expired before the org finished signing you in. Please try again.",
    state_mismatch: "Login could not be verified (state mismatch). Please try again.",
    token_exchange_failed:
      "Okta rejected the code exchange. Double-check the Client ID/Secret and that the redirect URI " +
      "http://localhost:5173/callback is registered on that app.",
  };
  return messages[code] ?? `Login failed: ${code}`;
}

export default function OrgConnectScreen() {
  const params = new URLSearchParams(window.location.search);
  const [orgDomain, setOrgDomain] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(errorMessage(params.get("error")));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { authorize_url } = await login({
        org_domain: orgDomain,
        client_id: clientId,
        client_secret: clientSecret || undefined,
      });
      window.location.assign(authorize_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start login");
      setSubmitting(false);
    }
  }

  return (
    <div className="centered">
      <form onSubmit={handleSubmit} className="org-connect-form">
        <h1>Okta AIAgent Visualiser</h1>
        <p>
          Connect to an Okta org to explore its AI Agents. This requires an OIDC app already
          registered in that org (redirect URI <code>http://localhost:5173/callback</code>), granted
          the required <code>okta.*</code> scopes and assigned to your admin account.
        </p>
        {error && <div className="error-banner">{error}</div>}
        <label>
          Org domain
          <input
            required
            placeholder="yourcompany.okta.com"
            value={orgDomain}
            onChange={(e) => setOrgDomain(e.target.value)}
          />
        </label>
        <label>
          Client ID
          <input required value={clientId} onChange={(e) => setClientId(e.target.value)} />
        </label>
        <label className="optional-field">
          <button type="button" className="link-button" onClick={() => setShowSecret((v) => !v)}>
            {showSecret ? "Hide" : "Add"} client secret (only if this is a confidential Web App, not a SPA)
          </button>
          {showSecret && (
            <input
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
            />
          )}
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Connecting..." : "Connect"}
        </button>
      </form>
    </div>
  );
}
