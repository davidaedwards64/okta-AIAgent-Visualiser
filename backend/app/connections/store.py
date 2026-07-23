import json
from pathlib import Path

from app.connections.models import SavedConnection

DATA_DIR = Path(__file__).resolve().parent.parent.parent / ".data"
CONNECTIONS_FILE = DATA_DIR / "connections.json"


class ConnectionsStore:
    """Flat JSON file of org_domain -> {client_id, client_secret}, keyed by
    normalized org domain.

    Unlike SessionStore, this must survive backend restarts — persisting known
    app registrations across runs is the whole point, so this can't be the
    same in-memory dict pattern.
    """

    def __init__(self, path: Path = CONNECTIONS_FILE) -> None:
        self._path = path

    def _read(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _write(self, data: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2))

    def list(self) -> list[SavedConnection]:
        return [SavedConnection(**v) for v in self._read().values()]

    def get(self, org_domain: str) -> SavedConnection | None:
        raw = self._read().get(org_domain)
        return SavedConnection(**raw) if raw else None

    def save(self, org_domain: str, client_id: str, client_secret: str | None) -> None:
        data = self._read()
        data[org_domain] = SavedConnection(
            org_domain=org_domain, client_id=client_id, client_secret=client_secret
        ).model_dump()
        self._write(data)

    def delete(self, org_domain: str) -> None:
        data = self._read()
        data.pop(org_domain, None)
        self._write(data)
