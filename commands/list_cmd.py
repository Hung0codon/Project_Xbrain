"""list — list AWS resources by type, filter by tag / missing-tag.

WHAT YOU MUST BUILD
-------------------
Support 4 resource types: ec2, rds, s3, volume.
Each takes:
- `want` — list of (key, value) tag pairs the resource MUST have
- `missing` — list of tag keys the resource MUST NOT have

Print a formatted table to stdout. Test cases are in tests/test_list.py.

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)            # "Owner=alice" -> ("Owner", "alice")
  tags_to_dict(items) -> dict       # boto3 [{"Key","Value"}] -> {k: v}
  tags_match(tags, want, missing) -> bool

AWS APIS YOU'LL NEED
--------------------
- EC2: ec2.describe_instances() with get_paginator
- RDS: rds.describe_db_instances(), then list_tags_for_resource(ResourceName=arn)
- S3:  s3.list_buckets(), then get_bucket_tagging(Bucket=name)
       (catch ClientError when bucket has no tagging config — treat as {})
- EBS: ec2.describe_volumes() with get_paginator

EXPECTED OUTPUT FORMAT (when run from CLI)
------------------------------------------
    EC2 Environment=dev — 1 found:
    ------------------------------------------------------------------------------
      i-0abc123def456789a       t3.micro       running       Environment=dev

VERIFY
------
    pytest tests/test_list.py -v
"""
import boto3
from botocore.exceptions import ClientError

from commands._common import parse_kv, tags_to_dict, tags_match


def _list_ec2(want, missing):
    """List EC2 instances matching tag filters."""
    ec2 = boto3.client("ec2")
    rows = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                state = inst.get("State", {}).get("Name", "unknown")
                if state == "terminated":
                    continue
                tags = tags_to_dict(inst.get("Tags"))
                if not tags_match(tags, want, missing):
                    continue
                rows.append((
                    inst["InstanceId"],
                    inst.get("InstanceType", "unknown"),
                    state,
                    tags,
                ))
    return rows


def _list_rds(want, missing):
    """List RDS DB instances matching tag filters."""
    rds = boto3.client("rds")
    rows = []
    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page.get("DBInstances", []):
            arn = db["DBInstanceArn"]
            try:
                tag_resp = rds.list_tags_for_resource(ResourceName=arn)
                tags = tags_to_dict(tag_resp.get("TagList"))
            except ClientError:
                tags = {}
            if not tags_match(tags, want, missing):
                continue
            rows.append((
                db["DBInstanceIdentifier"],
                db.get("DBInstanceClass", "unknown"),
                db.get("DBInstanceStatus", "unknown"),
                tags,
            ))
    return rows


def _list_s3(want, missing):
    """List S3 buckets matching tag filters."""
    s3 = boto3.client("s3")
    rows = []
    for b in s3.list_buckets().get("Buckets", []):
        name = b["Name"]
        try:
            tag_resp = s3.get_bucket_tagging(Bucket=name)
            tags = tags_to_dict(tag_resp.get("TagSet"))
        except ClientError:
            tags = {}
        if not tags_match(tags, want, missing):
            continue
        rows.append((name, "bucket", "active", tags))
    return rows


def _list_volume(want, missing):
    """List EBS volumes matching tag filters."""
    ec2 = boto3.client("ec2")
    rows = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate():
        for vol in page.get("Volumes", []):
            tags = tags_to_dict(vol.get("Tags"))
            if not tags_match(tags, want, missing):
                continue
            type_size = f"{vol.get('VolumeType', 'unknown')}-{vol.get('Size', 0)}GB"
            rows.append((
                vol["VolumeId"],
                type_size,
                vol.get("State", "unknown"),
                tags,
            ))
    return rows


DISPATCH = {
    "ec2": _list_ec2,
    "rds": _list_rds,
    "s3": _list_s3,
    "volume": _list_volume,
}


def _format_tags(tags):
    if not tags:
        return "(no tags)"
    return " ".join(f"{k}={v}" for k, v in sorted(tags.items()))


def _header(rtype, want, missing, count):
    bits = []
    for k, v in want:
        bits.append(f"{k}={v}")
    for k in missing:
        bits.append(f"missing:{k}")
    filter_str = " ".join(bits) if bits else "(no filter)"
    return f"{rtype.upper()} {filter_str} — {count} found:"


def run(args):
    """Entry point called by costctl.py."""
    want = [parse_kv(s) for s in (args.tag or [])]
    missing = list(args.missing_tag or [])
    rows = DISPATCH[args.type](want, missing)
    print(_header(args.type, want, missing, len(rows)))
    print("-" * 78)
    for rid, rtype_or_class, state, tags in rows:
        print(f"  {rid:<24} {rtype_or_class:<14} {state:<13} {_format_tags(tags)}")
