"""
Rotate the production database password and check that RDS is not open to
the internet. Run ON the EC2 box, as root, with the app's own venv:

    sudo /opt/atlantic-highlands/api/venv/bin/python \
         /opt/atlantic-highlands/infra/security/rotate_db_password.py            # report only
    sudo ... rotate_db_password.py --rotate                                      # new password
    sudo ... rotate_db_password.py --lockdown                                    # close 5432 to the world
    sudo ... rotate_db_password.py --rotate --lockdown

Why it exists: earlier versions of setup_secrets.py and sync_to_aws.sh put the
RDS host, master user and password in git, and this repo is public. Deleting
them from history does not un-publish them; rotating the password and
closing the network path does.

--rotate
  * reads the live DATABASE_URL exactly as the app does (Secrets Manager
    when AWS_SECRETS_NAME is set, else /etc/atlantic-highlands.env);
  * changes the password with ALTER ROLE over that connection, so it needs
    no RDS API permission;
  * proves the new password connects, then writes it everywhere the app
    reads it (the secret's DATABASE_URL/RDS_PASSWORD, the env file);
  * if any write fails it puts the OLD password back, so the site is never
    left with a password nothing knows;
  * restarts ah-api and checks it stays up.
  The password is never printed, logged or passed on a command line.

--lockdown (needs ec2:Describe*/Authorize*/Revoke* and rds:Describe*)
  * allows 5432 from this box's own security group(s), then removes any
    0.0.0.0/0 or ::/0 rule on 5432 from the RDS security groups.
  Anything that connects from outside AWS (a laptop .env pointing at prod)
  stops working; that is the point.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ENV_FILE = "/etc/atlantic-highlands.env"
SERVICE = "ah-api"


def say(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"!! {msg}", flush=True)


# ── where the app gets its URL ───────────────────────────────────────────────

def read_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_secret(env: dict[str, str]):
    """(client, secret_id, dict) or (None, None, {}) — mirrors api/config.py."""
    name = env.get("AWS_SECRETS_NAME") or os.getenv("AWS_SECRETS_NAME", "")
    if not name:
        return None, None, {}
    import boto3

    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        if env.get(k) and not os.getenv(k):
            os.environ[k] = env[k]
    region = env.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    value = json.loads(client.get_secret_value(SecretId=name)["SecretString"])
    return client, name, value


def with_password(url: str, password: str) -> str:
    p = urlsplit(url)
    user = p.username or ""
    host = p.hostname or ""
    port = f":{p.port}" if p.port else ""
    netloc = f"{quote(unquote(user), safe='')}:{quote(password, safe='')}@{host}{port}"
    return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))


def new_password() -> str:
    # RDS forbids / @ " and space; stay alphanumeric so every client (URL,
    # .env, psql) takes it unescaped.
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(40))


def connect(url: str):
    import psycopg2

    return psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://"), connect_timeout=10)


def set_password(conn, password: str) -> None:
    """ALTER ROLE over an already-open session (it outlives the change, so the
    same session can always put the old password back)."""
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER ROLE CURRENT_USER WITH PASSWORD {}").format(sql.Literal(password))
        )


# ── writes ───────────────────────────────────────────────────────────────────

def write_env_url(path: str, url: str) -> str:
    """Replace DATABASE_URL in place; return the backup path."""
    backup = f"{path}.bak-{datetime.now():%Y%m%d-%H%M%S-%f}"
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    lines = open(path).read().splitlines(keepends=True)
    with open(path, "w") as fh:
        for line in lines:
            fh.write(f"DATABASE_URL={url}\n" if line.lstrip().startswith("DATABASE_URL=") else line)
    os.chmod(path, 0o600)
    return backup


def write_secret(client, secret_id: str, current: dict, url: str, password: str) -> None:
    updated = dict(current)
    if "DATABASE_URL" in updated:
        updated["DATABASE_URL"] = url
    if "RDS_PASSWORD" in updated:
        updated["RDS_PASSWORD"] = password
    client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(updated))


def restart_and_check() -> bool:
    subprocess.run(["systemctl", "restart", SERVICE], check=False)
    time.sleep(8)
    active = subprocess.run(["systemctl", "is-active", SERVICE], capture_output=True, text=True).stdout.strip()
    say(f"   {SERVICE}: {active}")
    return active == "active"


# ── rotate ───────────────────────────────────────────────────────────────────

def rotate(env_file: str, restart: bool) -> int:
    env = read_env_file(env_file)
    try:
        client, secret_id, secret = load_secret(env)
    except Exception as e:  # noqa: BLE001
        warn(f"AWS_SECRETS_NAME is set but the secret can't be read ({e}).")
        warn("The app would fall back to the env file; refusing to guess. Fix access and re-run.")
        return 1

    in_secret = "DATABASE_URL" in secret
    in_env = "DATABASE_URL" in env
    old_url = secret.get("DATABASE_URL") if in_secret else env.get("DATABASE_URL")
    if not old_url:
        warn(f"No DATABASE_URL in Secrets Manager or {env_file}.")
        return 1
    if in_secret and in_env and urlsplit(env["DATABASE_URL"]).password != urlsplit(old_url).password:
        say(f"   note: {env_file} holds a different (stale) password than the secret; both get the new one.")

    p = urlsplit(old_url)
    say(f"== Rotating password for role {p.username} on {p.hostname}")
    say(f"   source of truth: {'Secrets Manager ' + secret_id if in_secret else env_file}")

    try:
        admin = connect(old_url)
        admin.autocommit = True
    except Exception as e:  # noqa: BLE001
        warn(f"Can't connect with the current password ({e}). Nothing changed.")
        return 1

    old_pw = unquote(p.password or "")
    pw = new_password()
    new_url = with_password(old_url, pw)

    set_password(admin, pw)
    try:
        connect(new_url).close()
    except Exception as e:  # noqa: BLE001
        warn(f"New password did not connect ({e}); restoring the old one.")
        set_password(admin, old_pw)
        return 1
    say("   new password set and verified")

    backup = None
    try:
        if in_secret:
            write_secret(client, secret_id, secret, new_url, pw)
            say(f"   Secrets Manager {secret_id}: updated")
        if in_env:
            backup = write_env_url(env_file, new_url)
            say(f"   {env_file}: updated (backup {backup})")
    except Exception as e:  # noqa: BLE001
        warn(f"Could not store the new password ({e}); rolling back.")
        set_password(admin, old_pw)
        if backup:
            shutil.copy2(backup, env_file)
        if in_secret:
            try:
                client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(secret))
            except Exception:  # noqa: BLE001
                pass
        warn("Old password restored; nothing else changed.")
        return 1

    admin.close()
    if restart:
        say(f"== Restarting {SERVICE}")
        if not restart_and_check():
            warn(f"{SERVICE} is not active. `journalctl -u {SERVICE} -n 50`. The new password IS in place.")
            return 1
    say("   Timers (scraper, digest, transcribe) read the same env/secret on their next run.")
    say("   Update any laptop .env that points at prod by hand — or better, stop doing that (see --lockdown).")
    return 0


# ── network ──────────────────────────────────────────────────────────────────

def _imds(path: str) -> str:
    tok = urllib.request.Request(
        "http://169.254.169.254/latest/api/token", method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
    )
    token = urllib.request.urlopen(tok, timeout=2).read().decode()
    req = urllib.request.Request(
        f"http://169.254.169.254/latest/meta-data/{path}",
        headers={"X-aws-ec2-metadata-token": token},
    )
    return urllib.request.urlopen(req, timeout=2).read().decode()


def network(env_file: str, lockdown: bool) -> int:
    import boto3
    from botocore.exceptions import ClientError

    env = read_env_file(env_file)
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        if env.get(k) and not os.getenv(k):
            os.environ[k] = env[k]
    region = env.get("AWS_REGION", "us-east-1")
    try:
        _, _, secret = load_secret(env)
    except Exception:  # noqa: BLE001
        secret = {}
    host = urlsplit(secret.get("DATABASE_URL") or env.get("DATABASE_URL", "")).hostname or ""
    say(f"== Network exposure of {host}")

    rds = boto3.client("rds", region_name=region)
    ec2 = boto3.client("ec2", region_name=region)
    try:
        db = next(
            d for d in rds.describe_db_instances()["DBInstances"]
            if d.get("Endpoint", {}).get("Address") == host
        )
    except StopIteration:
        warn(f"No RDS instance with endpoint {host} in {region}.")
        return 1
    except Exception as e:  # noqa: BLE001
        warn(f"Can't describe RDS ({e}). Check by hand: RDS console → {host.split('.')[0]} → "
             "Connectivity & security → 'Publicly accessible' and the VPC security group's inbound rules.")
        return 1

    public = db["PubliclyAccessible"]
    db_sgs = [g["VpcSecurityGroupId"] for g in db["VpcSecurityGroups"]]
    say(f"   publicly accessible: {public}")
    open_rules = []
    for sg in ec2.describe_security_groups(GroupIds=db_sgs)["SecurityGroups"]:
        for perm in sg["IpPermissions"]:
            lo, hi = perm.get("FromPort", 0), perm.get("ToPort", 65535)
            proto = perm.get("IpProtocol")
            covers = proto == "-1" or (lo <= 5432 <= hi)
            world4 = [r for r in perm.get("IpRanges", []) if r["CidrIp"] == "0.0.0.0/0"]
            world6 = [r for r in perm.get("Ipv6Ranges", []) if r["CidrIpv6"] == "::/0"]
            others = [r["CidrIp"] for r in perm.get("IpRanges", []) if r["CidrIp"] != "0.0.0.0/0"]
            groups = [g["GroupId"] for g in perm.get("UserIdGroupPairs", [])]
            if covers:
                say(f"   {sg['GroupId']} {proto} {lo}-{hi}: cidrs={[*(r['CidrIp'] for r in world4), *others, *(r['CidrIpv6'] for r in world6)]} groups={groups}")
            if covers and (world4 or world6):
                open_rules.append((sg["GroupId"], perm, world4, world6))

    exposed = public and open_rules
    if exposed:
        warn("RDS is reachable from the whole internet on 5432. Anyone with the leaked password can log in.")
    elif open_rules:
        say("   0.0.0.0/0 rule exists but the instance is not publicly accessible (no public IP): not reachable from outside the VPC.")
    else:
        say("   no world-open rule on 5432")

    if not lockdown:
        if open_rules:
            say("   re-run with --lockdown to remove it")
        return 2 if exposed else 0

    try:
        my_sgs = _imds("security-groups")
        mac = _imds("mac")
        my_sg_ids = _imds(f"network/interfaces/macs/{mac}/security-group-ids").split()
    except Exception as e:  # noqa: BLE001
        warn(f"Not on EC2 / no metadata ({e}); run --lockdown on the box itself.")
        return 1
    shared = sorted(set(db_sgs) & set(my_sg_ids))
    if shared:
        warn(f"The DB and this box share security group(s) {shared}. Removing its world rule would also cut "
             "SSH/HTTPS to the site. Give the DB its own group (RDS console → Modify → Security group), "
             "then re-run --lockdown.")
        return 1
    say(f"== Lockdown: allowing 5432 from this box's group(s) {my_sg_ids} ({my_sgs.split()})")
    for db_sg in db_sgs:
        for mine in my_sg_ids:
            try:
                ec2.authorize_security_group_ingress(
                    GroupId=db_sg,
                    IpPermissions=[{"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
                                    "UserIdGroupPairs": [{"GroupId": mine, "Description": "app box"}]}],
                )
                say(f"   {db_sg}: + {mine}")
            except ClientError as e:
                if "Duplicate" not in str(e):
                    warn(f"{db_sg}: could not add {mine} ({e}); NOT removing the open rule.")
                    return 1
                say(f"   {db_sg}: {mine} already allowed")

    # The box is now allowed by group; cut the world rule, then prove the box still connects.
    url = secret.get("DATABASE_URL") or env.get("DATABASE_URL")
    for sg_id, perm, world4, world6 in open_rules:
        ec2.revoke_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{k: v for k, v in {
                "IpProtocol": perm["IpProtocol"],
                "FromPort": perm.get("FromPort"),
                "ToPort": perm.get("ToPort"),
                "IpRanges": [{"CidrIp": r["CidrIp"]} for r in world4] or None,
                "Ipv6Ranges": [{"CidrIpv6": r["CidrIpv6"]} for r in world6] or None,
            }.items() if v is not None}],
        )
        say(f"   {sg_id}: removed world access")
    time.sleep(3)
    try:
        connect(url).close()
        say("   box → DB still connects")
    except Exception as e:  # noqa: BLE001
        warn(f"Box can no longer reach the DB ({e}). Restore with the console: add an inbound 5432 rule "
             f"to {db_sgs} from {my_sg_ids}.")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rotate", action="store_true", help="set a new DB password everywhere the app reads it")
    ap.add_argument("--lockdown", action="store_true", help="remove world access to 5432 on the RDS security groups")
    ap.add_argument("--env-file", default=ENV_FILE)
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--skip-network", action="store_true")
    a = ap.parse_args()

    if (a.rotate or a.lockdown) and os.geteuid() != 0 and a.env_file == ENV_FILE:
        warn("run with sudo")
        return 1
    rc = 0
    if a.rotate:
        rc = rotate(a.env_file, restart=not a.no_restart)
        if rc:
            return rc
    if not a.skip_network:
        rc = network(a.env_file, a.lockdown) or rc
    elif not a.rotate:
        say("nothing to do")
    return rc


if __name__ == "__main__":
    sys.exit(main())
