"""idle — (stretch) find idle EC2 instances by N-hour CPU average."""
import boto3
from datetime import datetime, timedelta, timezone

from commands._common import tags_to_dict


def _avg_cpu(cw, instance_id, hours):
    """Return average CPU% over last N hours, or None if no datapoints."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    resp = cw.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=3600,
        Statistics=["Average"],
    )
    points = resp.get("Datapoints", [])
    if not points:
        return None
    return sum(p["Average"] for p in points) / len(points)


def run(args):
    """Entry point."""
    ec2 = boto3.client("ec2")
    cw = boto3.client("cloudwatch")

    print(f"Scanning running EC2 (excluding keep=true) — threshold {args.threshold}% over {args.hours}h:")
    print("-" * 78)

    idle_ids = []
    for page in ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                tags = tags_to_dict(inst.get("Tags"))
                if tags.get("keep") == "true":
                    continue
                iid = inst["InstanceId"]
                itype = inst.get("InstanceType", "unknown")
                avg = _avg_cpu(cw, iid, args.hours)
                if avg is None:
                    print(f"  {iid:<22} {itype:<12} cpu_{args.hours}h=NO DATA")
                    continue
                marker = "  <- IDLE" if avg < args.threshold else ""
                print(f"  {iid:<22} {itype:<12} cpu_{args.hours}h={avg:5.2f}%{marker}")
                if avg < args.threshold:
                    idle_ids.append(iid)

    print("-" * 78)
    print()
    print(f"Idle: {len(idle_ids)} instance(s): {idle_ids}")
    if idle_ids:
        print("Tip: combo with terminate →  ./costctl.py terminate ec2 --id <id>")
