import { useEffect, useState } from "react";
import { getMe } from "./api/auth";
import GraphScreen from "./screens/GraphScreen";
import OrgConnectScreen from "./screens/OrgConnectScreen";
import RiskReportScreen from "./screens/RiskReportScreen";

type ConnectionState = "checking" | "disconnected" | "connected";

// No router needed for these screens — /callback is intercepted server-side
// before the SPA ever renders it, and the risk report is a query-param
// branch (opened via window.open) rather than a real route. Add a router
// later if more screens appear.
export default function App() {
  const [state, setState] = useState<ConnectionState>("checking");
  const [orgDomain, setOrgDomain] = useState<string | null>(null);

  const isRiskReport = new URLSearchParams(window.location.search).get("view") === "risk-report";

  useEffect(() => {
    getMe()
      .then((me) => {
        if (me.connected) {
          setOrgDomain(me.org_domain ?? null);
          setState("connected");
        } else {
          setState("disconnected");
        }
      })
      .catch(() => setState("disconnected"));
  }, []);

  if (isRiskReport) return <RiskReportScreen />;

  if (state === "checking") return <div className="centered">Loading...</div>;

  if (state === "connected" && orgDomain) {
    return <GraphScreen orgDomain={orgDomain} onDisconnected={() => setState("disconnected")} />;
  }

  return <OrgConnectScreen />;
}
