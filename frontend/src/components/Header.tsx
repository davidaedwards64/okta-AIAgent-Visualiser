interface HeaderProps {
  orgDomain: string;
  onRefresh: () => void;
  onDisconnect: () => void;
  refreshing: boolean;
}

export default function Header({ orgDomain, onRefresh, onDisconnect, refreshing }: HeaderProps) {
  return (
    <header className="app-header">
      <span className="app-title">Okta AIAgent Visualiser</span>
      <span className="org-domain">{orgDomain}</span>
      <div className="header-actions">
        <button onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
        <button onClick={onDisconnect}>Disconnect</button>
      </div>
    </header>
  );
}
