"""terminate — terminate or delete one resource, with safety confirmation.

WHAT YOU MUST BUILD
-------------------
4 dispatch functions, one per resource type, that:
  - Ask `confirm(...)` before doing the destructive call (unless --force)
  - Perform the right boto3 API call
  - Handle ClientError gracefully (no stack trace dump)

Safety contract — DO NOT break this:
  - `terminate` MUST ask y/N confirmation by default
  - `--force` bypasses confirm (for CI / scripted use)
  - S3 MUST refuse to delete buckets that still contain objects
  - Any AWS error MUST print a friendly message, not a Python traceback

HELPERS YOU CAN USE
-------------------
From commands._common:
  confirm(prompt, force=False) -> bool

AWS APIS YOU'LL NEED
--------------------
- EC2: ec2.terminate_instances(InstanceIds=[id])
- RDS: rds.stop_db_instance(DBInstanceIdentifier=id)
- S3:  s3.list_objects_v2(Bucket=name).get("KeyCount", 0)
       s3.delete_bucket(Bucket=name)
- EBS: ec2.delete_volume(VolumeId=id)
"""
import boto3
from botocore.exceptions import ClientError

from commands._common import confirm


def _terminate_ec2(rid, force):
    if not confirm(f"Terminate EC2 instance {rid}?", force=force):
        print("Aborted.")
        return
    ec2 = boto3.client("ec2")
    ec2.terminate_instances(InstanceIds=[rid])
    print(f"Terminated EC2 {rid}")


def _terminate_rds(rid, force):
    if not confirm(f"Stop RDS instance {rid}?", force=force):
        print("Aborted.")
        return
    rds = boto3.client("rds")
    rds.stop_db_instance(DBInstanceIdentifier=rid)
    print(f"Stopped RDS {rid}")


def _terminate_s3(rid, force):
    s3 = boto3.client("s3")
    resp = s3.list_objects_v2(Bucket=rid)
    count = resp.get("KeyCount", 0)
    if count > 0:
        print(f"Refusing — bucket {rid} has {count} object(s). Empty it first.")
        return
    if not confirm(f"Delete S3 bucket {rid}?", force=force):
        print("Aborted.")
        return
    s3.delete_bucket(Bucket=rid)
    print(f"Deleted S3 bucket {rid}")


def _terminate_volume(rid, force):
    if not confirm(f"Delete EBS volume {rid}?", force=force):
        print("Aborted.")
        return
    ec2 = boto3.client("ec2")
    ec2.delete_volume(VolumeId=rid)
    print(f"Deleted EBS volume {rid}")


DISPATCH = {
    "ec2": _terminate_ec2,
    "rds": _terminate_rds,
    "s3": _terminate_s3,
    "volume": _terminate_volume,
}


def run(args):
    """Entry point."""
    fn = DISPATCH[args.type]
    try:
        fn(args.id, args.force)
    except ClientError as e:
        err = e.response.get("Error", {})
        code = err.get("Code", "Unknown")
        msg = err.get("Message", str(e))
        print(f"AWS error [{code}]: {msg}")
