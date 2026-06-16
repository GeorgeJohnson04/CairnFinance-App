"""Import a 'Finance Project.xlsx' workbook into a Cairn user.

Examples:
    # Import into an existing user
    python import_excel.py --file "..\\Finance\\Finance Project.xlsx" --email you@example.com

    # Create the user first (prompts for a password), then import
    python import_excel.py --file "..\\Finance\\Finance Project.xlsx" --email you@example.com --create --name "Your Name"

    # Wipe the user's existing portfolio and re-import fresh
    python import_excel.py --file "..." --email you@example.com --replace
"""
import argparse
import getpass
import os
import sys

from app import create_app
from app.db import get_db
from app.security import hash_password, password_problems, valid_email
from app.services.importer import import_workbook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Path to the .xlsx")
    parser.add_argument("--email", required=True, help="User to import into")
    parser.add_argument("--create", action="store_true",
                        help="Create the user if they don't exist")
    parser.add_argument("--name", default="", help="Name for --create")
    parser.add_argument("--replace", action="store_true",
                        help="Delete the user's existing portfolio first")
    args = parser.parse_args()

    path = os.path.abspath(args.file)
    if not os.path.exists(path):
        sys.exit(f"File not found: {path}")
    email = args.email.strip().lower()
    if not valid_email(email):
        sys.exit("That email address doesn't look valid.")

    app = create_app()
    with app.app_context():
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?",
                          (email,)).fetchone()
        if user is None:
            if not args.create:
                sys.exit(f"No user with email {email}. "
                         "Add --create to create one.")
            name = args.name.strip() or email.split("@")[0].title()
            while True:
                pw = getpass.getpass(f"Choose a password for {email}: ")
                problems = password_problems(pw)
                if problems:
                    print("  " + " ".join(problems))
                    continue
                if pw != getpass.getpass("Confirm password: "):
                    print("  Passwords don't match, try again.")
                    continue
                break
            cur = db.execute(
                "INSERT INTO users (email, name, pw_hash) VALUES (?, ?, ?)",
                (email, name, hash_password(pw)))
            db.commit()
            user_id = cur.lastrowid
            print(f"Created user {name} <{email}>")
        else:
            user_id = user["id"]

        counts, notes = import_workbook(db, user_id, path,
                                        replace=args.replace)

    print("\nImported:")
    for key, value in counts.items():
        print(f"  {key:>14}: {value}")
    print("\nCorrections applied (vs. the Excel workbook):")
    for note in notes:
        print(f"  • {note}")
    print("\nDone! Start the app with:  python run.py")


if __name__ == "__main__":
    main()
