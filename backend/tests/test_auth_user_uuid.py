from uuid import UUID

from app.core.auth import CurrentUser


def test_user_uuid_accepts_non_uuid_token_id_with_stable_fallback():
    user = CurrentUser(oid="msa-sub-not-a-uuid", email="x@example.com")
    derived = user.user_uuid
    assert isinstance(derived, UUID)
    # Deterministic mapping
    assert derived == CurrentUser(oid="msa-sub-not-a-uuid").user_uuid
