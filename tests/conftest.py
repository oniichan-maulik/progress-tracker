import pytest
from sqlalchemy.orm import sessionmaker

from core.db import init_db, make_engine
from core.models import ROLE_ADMIN, ROLE_EMPLOYEE
from core.services import create_user


@pytest.fixture
def session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def admin(session):
    return create_user(session, "boss", "Bea Boss", "adminpass1", ROLE_ADMIN)


@pytest.fixture
def alice(session):
    return create_user(session, "alice", "Alice Archer", "alicepass1", ROLE_EMPLOYEE)


@pytest.fixture
def bob(session):
    return create_user(session, "bob", "Bob Baker", "bobpass12", ROLE_EMPLOYEE)
