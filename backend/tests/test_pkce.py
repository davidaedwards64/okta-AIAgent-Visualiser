import base64
import hashlib

from app.auth.pkce import generate_pkce_pair, generate_state


def test_generate_state_is_url_safe_and_nonempty():
    state = generate_state()
    assert state
    assert all(c.isalnum() or c in "-_" for c in state)


def test_pkce_pair_challenge_matches_verifier():
    verifier, challenge = generate_pkce_pair()
    expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
    assert challenge == expected_challenge


def test_pkce_pairs_are_unique():
    verifier1, challenge1 = generate_pkce_pair()
    verifier2, challenge2 = generate_pkce_pair()
    assert verifier1 != verifier2
    assert challenge1 != challenge2
