import base64
import hashlib
import secrets


def generate_state() -> str:
    return secrets.token_urlsafe(24)


def generate_pkce_pair() -> tuple[str, str]:
    """Returns (verifier, challenge) for PKCE with S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
