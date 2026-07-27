import os
from datetime import datetime
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
    print("available aspsps:")
    pprint(r.json()["aspsps"])


if __name__ == "__main__":
    main()
