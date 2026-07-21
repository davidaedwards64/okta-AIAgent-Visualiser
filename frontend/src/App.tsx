import { useEffect, useState } from "react";
import { getMe } from "./api/auth";
import GraphScreen from "./screens/GraphScreen";
import OrgConnectScreen from "./screens/OrgConnectScreen";

type ConnectionState = "checking" | "disconnected" | "connected";

// No router needed for two screens — /callback is intercepted server-side
// before the SPA ever renders it. Add a router later if more screens appear.
export default function App() {
  const [state, setState] = useState<ConnectionState>("checking");
  const [orgDomain, setOrgDomain] = useState<string | null>(null);

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

  if (state === "checking") return <div className="centered">Loading...</div>;

  if (state === "connected" && orgDomain) {
    return <GraphScreen orgDomain={orgDomain} onDisconnected={() => setState("disconnected")} />;
  }

  return <OrgConnectScreen />;
}
