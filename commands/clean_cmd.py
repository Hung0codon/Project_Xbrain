"""clean — (stretch) bulk terminate resources matching a tag.

WARNING — DESIGN-FOR-SAFETY
---------------------------
This is the most dangerous command in the CLI. Get the contract right:

  1. DEFAULT IS DRY-RUN. Without --apply the command MUST NOT touch resources.
  2. Skip terminated/shutting-down instances (already gone).
  3. Skip in-use volumes (can't delete while attached).
"""
import boto3
from botocore.exceptions import ClientError

from commands._common import parse_kv, tags_to_dict


_TERMINAL_EC2_STATES = {"terminated", "shutting-down"}


def _find_targets(tag_key, tag_val):
    """Return {"ec2": [...], "volume": [...]} matching tag in non-terminal state."""
    ec2 = boto3.client("ec2")
    targets = {"ec2": [], "volume": []}

    for page in ec2.get_paginator("describe_instances").paginate():
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                state = inst.get("State", {}).get("Name", "unknown")
                if state in _TERMINAL_EC2_STATES:
                    continue
                tags = tags_to_dict(inst.get("Tags"))
                if tags.get(tag_key) == tag_val:
                    targets["ec2"].append(inst["InstanceId"])

    for page in ec2.get_paginator("describe_volumes").paginate():
        for vol in page.get("Volumes", []):
            if vol.get("State") != "available":
                continue
            tags = tags_to_dict(vol.get("Tags"))
            if tags.get(tag_key) == tag_val:
                targets["volume"].append(vol["VolumeId"])

    return targets


def run(args):
    """Entry point."""
    key, val = parse_kv(args.tag)
    targets = _find_targets(key, val)
    n_ec2 = len(targets["ec2"])
    n_vol = len(targets["volume"])

    if n_ec2 == 0 and n_vol == 0:
        print(f"Nothing to clean for {key}={val}.")
        return

    print(f"Targets for {key}={val}: {n_ec2} EC2 instance(s), {n_vol} volume(s)")
    print("-" * 78)
    for iid in targets["ec2"]:
        print(f"  EC2     {iid}")
    for vid in targets["volume"]:
        print(f"  VOLUME  {vid}")
    print("-" * 78)

    if not args.apply:
        print("(dry-run — pass --apply to actually terminate)")
        return

    ec2 = boto3.client("ec2")
    if targets["ec2"]:
        try:
            ec2.terminate_instances(InstanceIds=targets["ec2"])
            print(f"Terminated {n_ec2} EC2 instance(s): {', '.join(targets['ec2'])}")
        except ClientError as e:
            err = e.response.get("Error", {})
            print(f"AWS error [{err.get('Code', 'Unknown')}]: {err.get('Message', str(e))}")

    for vid in targets["volume"]:
        try:
            ec2.delete_volume(VolumeId=vid)
            print(f"Deleted volume {vid}")
        except ClientError as e:
            err = e.response.get("Error", {})
            print(f"AWS error [{err.get('Code', 'Unknown')}] on {vid}: {err.get('Message', str(e))}")
