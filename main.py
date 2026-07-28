import os
from datetime import date, datetime, timedelta, timezone
from pprint import pprint

import jwt as pyjwt
import requests

APPLICATION_ID = "021064f6-2e5d-45d2-9602-7fa344788038"
with open("enablebanking_private.pem") as f:
    private_key = f.read()

iat = int(datetime.now().timestamp())

jwt_body = {
    "iss": "enablebanking.com",
    "aud": "api.enablebanking.com",
    "iat": iat,
    "exp": iat + 3600,
}

jwt = pyjwt.encode(
    jwt_body, private_key, algorithm="RS256", headers={"kid": APPLICATION_ID}
)

base_headers = {"Authorization": f"Bearer {jwt}"}


def main():
    r = requests.get(
        "https://api.enablebanking.com/aspsps?country=DE", headers=base_headers
    )
    #    print("available aspsps:")
    # pprint(r.json()["aspsps"])
    bank_name = "Aachener Bank"
    body = {
        "access": {
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        },
        "aspsp": {"name": bank_name, "country": "EN"},
        "state": APPLICATION_ID,
        "redirect_url": "http://localhost:8000/api/auth",
        "psu_type": "personal",
    }

    r = requests.post(
        "https://api.enablebanking.com/auth", json=body, headers=base_headers
    )

    pprint(r.json()["aspsps"])

    auth_url = r.json()["url"]
    print(f"auth url: {auth_url}")
    code = input("code: ")
    r = requests.post(
        f"https://api.enablebanking.com/sessions",
        json={"code": code},
        headers=base_headers,
    )
    session = r.json()
    print("new user session:")
    pprint(session)

    account_uid = session["accounts"][0]["uid"]

    r = requests.get(
        f"https://api.enablebanking.com/accounts/{account_uid}/balances",
        headers=base_headers,
    )
    print("balance:")
    pprint(r.json)


if __name__ == "__main__":
    main()
