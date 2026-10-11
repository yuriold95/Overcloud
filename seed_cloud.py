"""Seed the deployed environment: migrate, seed the sample org, and create the Cognito demo
users with generated passwords stored only in SSM Parameter Store (SecureString).

Usage: AWS_PROFILE=... python scripts/seed_cloud.py .cdk-outputs.json
The passwords are never printed; read one with:
  aws ssm get-parameter --with-decryption --name /overclouded/demo-users/user-priya
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import string
import sys
from pathlib import Path

import boto3


def _outputs(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text())
    flat: dict[str, str] = {}
    for stack in data.values():
        flat.update(stack)
    return flat


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(20))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
        ):
            return pw


async def _seed() -> None:
    from overclouded.demo.seed import seed_sample_org
    from overclouded.repos.client import close_client, get_db
    from overclouded.repos.migrate import migrate
    from overclouded.settings import get_settings

    settings = get_settings()
    db = await get_db(settings)
    await migrate(db)
    await seed_sample_org(db, settings)
    await close_client()


async def _set_subs(subs: dict[str, str]) -> None:
    from overclouded.demo.catalog import SAMPLE_ORG_ID
    from overclouded.repos.client import close_client, get_db
    from overclouded.repos.collections import Repos
    from overclouded.settings import get_settings

    db = await get_db(get_settings())
    repos = Repos(db, SAMPLE_ORG_ID)
    for user_id, sub in subs.items():
        await repos.users.update_one({"_id": user_id}, {"$set": {"cognito_sub": sub}})
    await close_client()


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: seed_cloud.py .cdk-outputs.json", file=sys.stderr)
        return 2
    out = _outputs(Path(argv[0]))
    region = os.environ.get("CDK_DEFAULT_REGION", "ap-south-1")
    os.environ["MONGODB_SECRET_ARN"] = out["MongoSecretArn"]
    os.environ.setdefault("AUTH_MODE", "cognito")
    os.environ["COGNITO_USER_POOL_ID"] = out["UserPoolId"]
    os.environ["COGNITO_APP_CLIENT_ID"] = out["UserPoolClientId"]
    asyncio.run(_seed())

    from overclouded.demo.catalog import SAMPLE_ORG_ID, USERS

    cognito = boto3.client("cognito-idp", region_name=region)
    ssm = boto3.client("ssm", region_name=region)
    subs: dict[str, str] = {}
    for u in USERS:
        attrs = [
            {"Name": "email", "Value": u.email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "name", "Value": u.name},
            {"Name": "custom:org_id", "Value": SAMPLE_ORG_ID},
            {"Name": "custom:role", "Value": u.role.value},
            {"Name": "custom:team_ids", "Value": ",".join(u.team_ids)},
        ]
        try:
            cognito.admin_create_user(
                UserPoolId=out["UserPoolId"],
                Username=u.email,
                UserAttributes=attrs,
                MessageAction="SUPPRESS",
            )
        except cognito.exceptions.UsernameExistsException:
            cognito.admin_update_user_attributes(
                UserPoolId=out["UserPoolId"], Username=u.email, UserAttributes=attrs
            )
        password = _password()
        cognito.admin_set_user_password(
            UserPoolId=out["UserPoolId"], Username=u.email, Password=password, Permanent=True
        )
        ssm.put_parameter(
            Name=f"/overclouded/demo-users/{u.id}",
            Value=password,
            Type="SecureString",
            Overwrite=True,
            Description=f"Sample Data Mode demo user {u.email} (fictional)",
        )
        user = cognito.admin_get_user(UserPoolId=out["UserPoolId"], Username=u.email)
        subs[u.id] = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
        print(
            f"demo user {u.email} ({u.role.value}) ready; password in SSM "
            f"/overclouded/demo-users/{u.id}"
        )
    asyncio.run(_set_subs(subs))
    print(f"Open {out.get('WebUrl', 'the WebUrl output')} and sign in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
