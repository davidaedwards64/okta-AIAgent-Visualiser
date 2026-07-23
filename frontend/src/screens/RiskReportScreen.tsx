import { useEffect, useState } from "react";
import { getRiskReport } from "../api/risk";
import type { RiskFinding, RiskLevel, RiskReportResponse } from "../types/risk";

const LEVEL_ORDER: RiskLevel[] = ["HIGH", "MEDIUM", "LOW"];

function groupByLevelThenAgent(findings: RiskFinding[]): Map<RiskLevel, Map<string, RiskFinding[]>> {
  const byLevel = new Map<RiskLevel, Map<string, RiskFinding[]>>();
  for (const level of LEVEL_ORDER) byLevel.set(level, new Map());
  for (const finding of findings) {
    const byAgent = byLevel.get(finding.level)!;
    const agentFindings = byAgent.get(finding.agent_name) ?? [];
    agentFindings.push(finding);
    byAgent.set(finding.agent_name, agentFindings);
  }
  return byLevel;
}

// The Risk Report tab is always opened via window.open() from a graph tab
// (see GraphScreen's handleOpenRiskReport), so window.opener normally points
// back at it — reuse that tab instead of opening yet another one. Closes
// this tab afterwards rather than just opener.focus(): browsers restrict
// scripts from stealing tab focus, so focus() alone doesn't reliably switch
// the visible tab, but closing a script-opened tab does return focus to
// whichever tab was active before it. Falls back to navigating this tab to
// the graph if the opener is gone (e.g. the graph tab was closed, or this
// URL was opened directly) — closing isn't possible/useful in that case.
function focusAgentInGraph(agentId: string) {
  const opener = window.opener as Window | null;
  if (opener && !opener.closed) {
    opener.postMessage({ type: "risk-report:focus-agent", agentId }, window.location.origin);
    window.close();
  } else {
    window.location.href = `/?focus=${encodeURIComponent(agentId)}`;
  }
}

// Generating the report is slow (it fans out group-membership fetches across
// every app an agent touches), and "View in graph" now closes this tab on
// every click — so reopening the Risk Report to check a second finding would
// otherwise pay that cost again. Instead, the graph tab that opened us holds
// the last report in memory (see GraphScreen's riskReportCacheRef) and hands
// it over here on request; only "Regenerate" bypasses this and re-fetches.
function requestCachedReport(): Promise<RiskReportResponse | null> {
  const opener = window.opener as Window | null;
  if (!opener || opener.closed) return Promise.resolve(null);
  return new Promise((resolve) => {
    let settled = false;
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      window.removeEventListener("message", handleReply);
      resolve(null);
    }, 500);
    function handleReply(event: MessageEvent) {
      if (settled || event.origin !== window.location.origin || event.data?.type !== "risk-report:cache") return;
      settled = true;
      clearTimeout(timeout);
      window.removeEventListener("message", handleReply);
      resolve(event.data.report ?? null);
    }
    window.addEventListener("message", handleReply);
    opener.postMessage({ type: "risk-report:request-cache" }, window.location.origin);
  });
}

function storeReportInOpener(report: RiskReportResponse) {
  const opener = window.opener as Window | null;
  if (opener && !opener.closed) {
    opener.postMessage({ type: "risk-report:store-cache", report }, window.location.origin);
  }
}

export default function RiskReportScreen() {
  const [report, setReport] = useState<RiskReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  function fetchFreshReport() {
    return getRiskReport().then((fresh) => {
      setReport(fresh);
      setFromCache(false);
      storeReportInOpener(fresh);
    });
  }

  useEffect(() => {
    requestCachedReport().then((cached) => {
      if (cached) {
        setReport(cached);
        setFromCache(true);
        return;
      }
      fetchFreshReport().catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load risk report"),
      );
    });
  }, []);

  function handleRegenerate() {
    setRegenerating(true);
    setError(null);
    fetchFreshReport()
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to regenerate risk report"))
      .finally(() => setRegenerating(false));
  }

  if (error) return <div className="centered error-banner">{error}</div>;
  if (!report) return <div className="centered">Analyzing risks...</div>;

  const grouped = groupByLevelThenAgent(report.findings);

  return (
    <div className="risk-report-screen">
      <header className="app-header">
        <span className="app-title">Risk Report</span>
        <span className="org-domain">{report.org_domain}</span>
        <div className="risk-report-actions">
          <span className="risk-report-generated-at">
            Generated {new Date(report.generated_at).toLocaleString()}
            {fromCache && " (cached)"}
          </span>
          <button type="button" onClick={handleRegenerate} disabled={regenerating}>
            {regenerating ? "Regenerating…" : "Regenerate"}
          </button>
        </div>
      </header>
      <div className="risk-report-body">
        {report.findings.length === 0 && <p>No risks identified.</p>}
        {LEVEL_ORDER.map((level) => {
          const byAgent = grouped.get(level)!;
          if (byAgent.size === 0) return null;
          return (
            <section key={level} className="risk-level-section">
              <h2 className={`risk-level-heading risk-level-${level.toLowerCase()}`}>{level}</h2>
              {[...byAgent.entries()].map(([agentName, findings]) => (
                <div key={agentName} className="risk-agent-group">
                  <h3 className="risk-agent-name">{agentName}</h3>
                  <ul className="risk-finding-list">
                    {findings.map((finding, i) => (
                      <li key={i} className="risk-finding">
                        <div className="risk-finding-header">
                          <span className={`risk-level-badge risk-level-${finding.level.toLowerCase()}`}>
                            {finding.level}
                          </span>
                          <span className="risk-rule-name">{finding.rule_name}</span>
                          <button
                            type="button"
                            className="risk-view-in-graph"
                            onClick={() => focusAgentInGraph(finding.agent_id)}
                          >
                            View in graph
                          </button>
                        </div>
                        <p className="risk-description">{finding.description}</p>
                        <p className="risk-detail">{finding.detail}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          );
        })}
        {report.warnings.length > 0 && (
          <details className="warnings-banner">
            <summary>{report.warnings.length} warning(s) while generating the risk report</summary>
            <ul>
              {report.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
