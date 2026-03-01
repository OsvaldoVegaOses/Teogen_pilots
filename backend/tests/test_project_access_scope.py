import uuid

from app.api.dependencies import (
    is_platform_super_admin,
    is_tenant_admin,
    project_scope_condition,
    resolve_project_tenant_id,
)
from app.core.auth import CurrentUser


def test_scope_condition_defaults_to_owner_scope():
    user = CurrentUser(oid=str(uuid.uuid4()), roles=["viewer"])
    sql = str(project_scope_condition(user))
    assert "projects.owner_id" in sql


def test_scope_condition_tenant_admin_includes_tenant_and_legacy_owner_fallback():
    user = CurrentUser(
        oid=str(uuid.uuid4()),
        tenant_id="tenant-a",
        roles=["tenant_admin"],
    )
    sql = str(project_scope_condition(user))
    assert "projects.tenant_id" in sql
    assert "projects.owner_id" in sql


def test_scope_condition_tenant_admin_without_tid_falls_back_to_owner_scope():
    user = CurrentUser(oid=str(uuid.uuid4()), roles=["tenant_admin"])
    assert not is_tenant_admin(user)
    sql = str(project_scope_condition(user))
    assert "projects.owner_id" in sql


def test_scope_condition_platform_super_admin_is_unrestricted():
    user = CurrentUser(oid=str(uuid.uuid4()), roles=["platform_super_admin"])
    assert is_platform_super_admin(user)
    sql = str(project_scope_condition(user)).lower()
    assert "owner_id" not in sql
    assert "tenant_id" not in sql


def test_resolve_project_tenant_id_uses_effective_scope():
    user_without_tid = CurrentUser(oid="msa-sub-not-a-uuid")
    assert resolve_project_tenant_id(user_without_tid).startswith("user:")

    user_with_tid = CurrentUser(oid="msa-sub-not-a-uuid", tenant_id="tenant-z")
    assert resolve_project_tenant_id(user_with_tid) == "tenant-z"
