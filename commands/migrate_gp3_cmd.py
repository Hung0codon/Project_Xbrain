"""migrate-gp3 — (stretch) plan or apply gp2 → gp3 EBS migration."""
import boto3
from botocore.exceptions import ClientError

GP2_PRICE = 0.10
GP3_PRICE = 0.08
DELTA = GP2_PRICE - GP3_PRICE


def _attached_id(vol):
    atts = vol.get("Attachments", [])
    if not atts:
        return "(none)"
    return atts[0].get("InstanceId", "(none)")


def _list_gp2_volumes(ec2):
    vols = []
    for page in ec2.get_paginator("describe_volumes").paginate(
        Filters=[{"Name": "volume-type", "Values": ["gp2"]}]
    ):
        vols.extend(page.get("Volumes", []))
    return vols


def _migrate_one(ec2, vid):
    ec2.modify_volume(
        VolumeId=vid,
        VolumeType="gp3",
        Iops=3000,
        Throughput=125,
    )
    print(f"  → modify_volume issued for {vid} (gp3, 3000 IOPS, 125 MiB/s)")


def run(args):
    """Entry point."""
    ec2 = boto3.client("ec2")

    if args.apply and args.volume_id:
        try:
            _migrate_one(ec2, args.volume_id)
            print()
            print("Volume entering 'modifying' → 'optimizing' state. App stays online.")
            print("Use `costctl list volume` after ~30 minutes to confirm 'in-use' + gp3.")
        except ClientError as e:
            err = e.response.get("Error", {})
            print(f"AWS error [{err.get('Code', 'Unknown')}]: {err.get('Message', str(e))}")
        return

    vols = _list_gp2_volumes(ec2)
    if not vols:
        print("No gp2 volumes found.")
        return

    print(f"gp2 volumes (price delta ${DELTA:.3f}/GB-month):")
    print("-" * 78)
    total_savings = 0.0
    for vol in vols:
        size = vol.get("Size", 0)
        savings = size * DELTA
        total_savings += savings
        attached = _attached_id(vol)
        print(f"  {vol['VolumeId']:<22} {size:>4}GB  attached={attached:<22} ${savings:>5.2f}/mo savings")
    print("-" * 78)
    print(f"  TOTAL projected savings: ${total_savings:.2f}/mo across {len(vols)} volume(s)")
    print()

    if not args.apply:
        print("(dry-run — pass --apply --volume-id <id> to migrate one, or --apply to migrate ALL)")
        return

    print("Applying migration to ALL gp2 volumes:")
    for vol in vols:
        try:
            _migrate_one(ec2, vol["VolumeId"])
        except ClientError as e:
            err = e.response.get("Error", {})
            print(f"  AWS error [{err.get('Code', 'Unknown')}] on {vol['VolumeId']}: {err.get('Message', str(e))}")
    print()
    print("Volume(s) entering 'modifying' → 'optimizing' state. App stays online.")
    print("Use `costctl list volume` after ~30 minutes to confirm 'in-use' + gp3.")
