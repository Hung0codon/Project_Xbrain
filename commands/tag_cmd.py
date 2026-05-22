"""tag — add or update tags on one resource.

WHAT YOU MUST BUILD
-------------------
4 dispatch functions, one per resource type. Each accepts a resource id
and a list of `{"Key": ..., "Value": ...}` dicts, and applies the tags.

AWS APIS YOU'LL NEED
--------------------
- EC2:    ec2.create_tags(Resources=[id], Tags=[{Key,Value}, ...])
- RDS:    rds.add_tags_to_resource(ResourceName=<ARN>, Tags=[...])
- S3:     s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": [...]})
            CAUTION: put_bucket_tagging REPLACES the entire tag set.
            Must merge with existing first.
"""
import boto3
from botocore.exceptions import ClientError

from commands._common import parse_kv


def _to_tags(set_args):
    """Convert ['k1=v1', 'k2=v2'] to [{'Key':'k1','Value':'v1'}, ...]."""
    out = []
    for s in set_args:
        k, v = parse_kv(s)
        out.append({"Key": k, "Value": v})
    return out


def _tag_ec2(rid, tags):
    ec2 = boto3.client("ec2")
    ec2.create_tags(Resources=[rid], Tags=tags)


def _tag_rds(rid, tags):
    rds = boto3.client("rds")
    arn = rds.describe_db_instances(DBInstanceIdentifier=rid)["DBInstances"][0]["DBInstanceArn"]
    rds.add_tags_to_resource(ResourceName=arn, Tags=tags)


def _tag_s3(rid, tags):
    s3 = boto3.client("s3")
    existing = {}
    try:
        resp = s3.get_bucket_tagging(Bucket=rid)
        for t in resp.get("TagSet", []):
            existing[t["Key"]] = t["Value"]
    except ClientError:
        existing = {}
    for t in tags:
        existing[t["Key"]] = t["Value"]
    tag_set = [{"Key": k, "Value": v} for k, v in existing.items()]
    s3.put_bucket_tagging(Bucket=rid, Tagging={"TagSet": tag_set})


def _tag_volume(rid, tags):
    ec2 = boto3.client("ec2")
    ec2.create_tags(Resources=[rid], Tags=tags)


DISPATCH = {
    "ec2": _tag_ec2,
    "rds": _tag_rds,
    "s3": _tag_s3,
    "volume": _tag_volume,
}


def run(args):
    """Entry point."""
    tags = _to_tags(args.set)
    try:
        DISPATCH[args.type](args.id, tags)
    except ClientError as e:
        err = e.response.get("Error", {})
        code = err.get("Code", "Unknown")
        msg = err.get("Message", str(e))
        print(f"AWS error [{code}]: {msg}")
        return
    summary = ", ".join(f"{t['Key']}={t['Value']}" for t in tags)
    print(f"Applied {len(tags)} tag(s) to {args.type} {args.id}: {summary}")
