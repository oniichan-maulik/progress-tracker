import pytest

from core.auth import authenticate, hash_password, verify_password
from core.models import ROLE_ADMIN, ROLE_EMPLOYEE
from core.services import (
    ServiceError,
    create_user,
    has_admin,
    reset_password,
    set_user_active,
    set_user_role,
)


def test_password_hash_roundtrip():
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")


def test_authenticate(session, alice):
    assert authenticate(session, "alice", "alicepass1").id == alice.id
    assert authenticate(session, "  ALICE ", "alicepass1").id == alice.id
    assert authenticate(session, "alice", "nope") is None
    assert authenticate(session, "ghost", "alicepass1") is None


def test_inactive_user_cannot_login(session, admin, alice):
    set_user_active(session, alice.id, False, actor=admin)
    assert authenticate(session, "alice", "alicepass1") is None


def test_create_user_validation(session, alice):
    with pytest.raises(ServiceError, match="taken"):
        create_user(session, "Alice", "Other", "password1", ROLE_EMPLOYEE)
    with pytest.raises(ServiceError, match="at least"):
        create_user(session, "carl", "Carl", "short", ROLE_EMPLOYEE)
    with pytest.raises(ServiceError, match="Username"):
        create_user(session, "bad name!", "X", "password1", ROLE_EMPLOYEE)
    with pytest.raises(ServiceError, match="role"):
        create_user(session, "dan", "Dan", "password1", "superuser")


def test_has_admin(session, alice):
    assert not has_admin(session)
    create_user(session, "root", "Root", "rootpass1", ROLE_ADMIN)
    assert has_admin(session)


def test_last_admin_and_self_protection(session, admin, alice):
    with pytest.raises(ServiceError, match="own account"):
        set_user_active(session, admin.id, False, actor=admin)
    other = create_user(session, "boss2", "Second Boss", "adminpass2", ROLE_ADMIN)
    set_user_active(session, admin.id, False, actor=other)
    with pytest.raises(ServiceError, match="one active admin"):
        set_user_active(session, other.id, False, actor=alice)
    with pytest.raises(ServiceError, match="own role"):
        set_user_role(session, other.id, ROLE_EMPLOYEE, actor=other)


def test_reset_password(session, alice):
    reset_password(session, alice.id, "brandnew99")
    assert authenticate(session, "alice", "brandnew99")
    assert authenticate(session, "alice", "alicepass1") is None
