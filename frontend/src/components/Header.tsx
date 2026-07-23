interface HeaderProps {
  orgDomain: string;
  onRefresh: () => void;
  onDisconnect: () => void;
  onExportPng: () => void;
  onOpenRiskReport: () => void;
  refreshing: boolean;
  showGroupMembers: boolean;
  onToggleGroupMembers: (checked: boolean) => void;
  togglingGroupMembers: boolean;
}

export default function Header({
  orgDomain,
  onRefresh,
  onDisconnect,
  onExportPng,
  onOpenRiskReport,
  refreshing,
  showGroupMembers,
  onToggleGroupMembers,
  togglingGroupMembers,
}: HeaderProps) {
  return (
    <header className="app-header">
      <span className="app-title">Okta AIAgent Visualiser</span>
      <span className="org-domain">{orgDomain}</span>
      <label className="group-members-toggle">
        <input
          type="checkbox"
          checked={showGroupMembers}
          disabled={togglingGroupMembers}
          onChange={(e) => onToggleGroupMembers(e.target.checked)}
        />
        {togglingGroupMembers ? "Loading members..." : "Show group members"}
      </label>
      <div className="header-actions">
        <button onClick={onExportPng} disabled={refreshing}>
          Export PNG
        </button>
        <button onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
        <button onClick={onOpenRiskReport}>Risk Report</button>
        <button onClick={onDisconnect}>Disconnect</button>
      </div>
    </header>
  );
}
