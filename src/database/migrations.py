from src.database.models import Base
from src.database.session import engine


def run_migrations():
    Base.metadata.create_all(bind=engine)
