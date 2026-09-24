import argparse
import getpass

from .auth import find_user, hasher
from .config import Settings
from .db import make_database
from .models import Role, User, LEGACY_ORG, Organization
from .schemas import NewUser


def main():
    parser = argparse.ArgumentParser(description="Create a Signal user. Password is entered securely.")
    parser.add_argument("email")
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=list(Role), default=Role.ADMIN)
    parser.add_argument(
        "--organization-id", default=LEGACY_ORG, help="Existing organization ID; defaults to migrated workspace"
    )
    args = parser.parse_args()
    password = getpass.getpass("Password (12+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    data = NewUser(email=args.email, password=password, name=args.name, role=args.role)
    engine, factory = make_database(Settings().database_url)
    with factory() as db:
        if db.get(Organization, args.organization_id) is None:
            raise SystemExit("Organization does not exist")
        if find_user(db, data.email):
            raise SystemExit("User already exists")
        db.add(
            User(
                email=data.email,
                name=data.name,
                role=data.role,
                organization_id=args.organization_id,
                password_hash=hasher.hash(data.password),
            )
        )
        db.commit()
    engine.dispose()
    print("User created. You can now sign in to Signal.")


if __name__ == "__main__":
    main()
