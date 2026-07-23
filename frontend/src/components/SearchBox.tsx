import { useMemo, useState } from "react";
import type { GraphResponse } from "../types/graph";

interface SearchBoxProps {
  graph: GraphResponse;
  onSelectResult: (nodeId: string) => void;
}

const MAX_RESULTS = 8;

export default function SearchBox({ graph, onSelectResult }: SearchBoxProps) {
  const [query, setQuery] = useState("");

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return graph.nodes.filter((n) => n.data.label.toLowerCase().includes(q)).slice(0, MAX_RESULTS);
  }, [graph, query]);

  function handleSelect(nodeId: string) {
    onSelectResult(nodeId);
    setQuery("");
  }

  return (
    <div className="search-box">
      <input
        type="text"
        placeholder="Search nodes by name..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {matches.length > 0 && (
        <ul className="search-results">
          {matches.map((n) => (
            <li key={n.data.id}>
              <button type="button" onClick={() => handleSelect(n.data.id)}>
                {n.data.label}
                <span className="search-result-type">{n.data.type}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
