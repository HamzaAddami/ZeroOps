
import string
import secrets


def generate_username(fullname: str, existing_usernames: list[str]) -> str:
    parts = fullname.lower().strip().split()

    if len(parts) >= 2:
        base = f"{parts[0]}.{parts[-1]}"
    else:
        base = parts[0]

    base = "".join(c for c in base if c.isalnum() or c == ".")

    username = base
    counter = 1
    while username in existing_usernames:
        username = f"{base}{counter}"
        counter += 1

    return username


def generate_temp_password(length: int = 12) -> str:
    if length < 8:
        length = 8

    alphabet = string.ascii_letters + string.digits + "!@#$%&*"

    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))

        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%&*" for c in password)):
            return password

def generate_initial_credentials(fullname:str, existing_usernames: list[str]) -> dict:
    username = generate_username(fullname, existing_usernames)
    password = generate_temp_password()
    return {
        "username": username,
        "password": password,
        "must_change_password": True
    }
