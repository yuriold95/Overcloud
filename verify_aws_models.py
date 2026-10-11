"""Re-verify every AWS operation and response field the adapters use against the installed
botocore service models (DECISIONS.md "AWS APIs — verified"). Exits 1 on any mismatch."""

from __future__ import annotations

import sys

import botocore
import botocore.session

REQUIRED: dict[str, dict[str, list[str]]] = {
    "compute-optimizer": {
        "GetEC2InstanceRecommendations": ["instanceRecommendations", "nextToken"],
        "GetEBSVolumeRecommendations": ["volumeRecommendations", "nextToken"],
        "GetIdleRecommendations": ["idleRecommendations", "nextToken"],
        "GetEnrollmentStatus": ["status"],
    },
    "cost-optimization-hub": {
        "ListRecommendations": ["items", "nextToken"],
        "GetRecommendation": ["recommendationId", "estimatedMonthlySavings"],
        "ListEnrollmentStatuses": ["items"],
    },
    "sustainability": {"GetEstimatedCarbonEmissions": ["Results", "NextToken"]},
    "cloudwatch": {"GetMetricData": ["MetricDataResults", "NextToken"]},
    "ec2": {
        "DescribeInstances": ["Reservations", "NextToken"],
        "DescribeVolumes": ["Volumes", "NextToken"],
        "DescribeSnapshots": ["Snapshots", "NextToken"],
        "DescribeInstanceTypes": ["InstanceTypes", "NextToken"],
    },
    "elbv2": {"DescribeTargetGroups": ["TargetGroups", "NextMarker"]},
    "scheduler": {"ListSchedules": ["Schedules", "NextToken"], "GetSchedule": ["Target"]},
    "sts": {"AssumeRole": ["Credentials"], "GetCallerIdentity": ["Account"]},
    "pricing": {"GetProducts": ["PriceList", "NextToken"]},
}
SHAPES: dict[str, dict[str, list[str]]] = {
    "compute-optimizer": {
        "InstanceRecommendation": [
            "instanceArn",
            "accountId",
            "currentInstanceType",
            "finding",
            "utilizationMetrics",
            "lookBackPeriodInDays",
            "recommendationOptions",
            "tags",
        ],
        "IdleRecommendation": [
            "resourceArn",
            "resourceId",
            "resourceType",
            "accountId",
            "finding",
            "savingsOpportunity",
            "utilizationMetrics",
            "lookBackPeriodInDays",
            "tags",
        ],
    },
    "cost-optimization-hub": {
        "Recommendation": [
            "recommendationId",
            "accountId",
            "region",
            "resourceId",
            "currentResourceType",
            "recommendedResourceType",
            "estimatedMonthlySavings",
            "actionType",
            "currencyCode",
        ],
    },
    "sustainability": {
        "EstimatedCarbonEmissions": [
            "TimePeriod",
            "DimensionsValues",
            "ModelVersion",
            "EmissionsValues",
        ],
    },
}


def main() -> int:
    session = botocore.session.get_session()
    errors: list[str] = []
    for service, ops in REQUIRED.items():
        model = session.get_service_model(service)
        for op, fields in ops.items():
            if op not in model.operation_names:
                errors.append(f"{service}.{op}: operation missing")
                continue
            out = model.operation_model(op).output_shape
            members = set(out.members) if out is not None else set()
            errors += [
                f"{service}.{op}: output field {f} missing" for f in fields if f not in members
            ]
    for service, shapes in SHAPES.items():
        model = session.get_service_model(service)
        for shape, fields in shapes.items():
            members = set(model.shape_for(shape).members)
            errors += [f"{service}.{shape}.{f} missing" for f in fields if f not in members]
    for e in errors:
        print(e, file=sys.stderr)
    print(f"botocore {botocore.__version__}: {'FAIL' if errors else 'OK'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
