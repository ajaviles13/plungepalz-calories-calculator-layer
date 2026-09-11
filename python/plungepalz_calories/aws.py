"""Optional DynamoDB profile fetch for the dispatcher recalculation path.

boto3 is imported lazily inside function bodies so the rest of the package
stays importable in a bare test environment with no AWS credentials.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_dynamodb = None

_PROFILE_ALIASES = {
    "#uh": "userHeight",
    "#uw": "userWeight",
    "#g": "gender",
    "#dob": "dateOfBirth",
    "#uom": "unitOfMeasure",
    "#prem": "isPremium",
}
_PROFILE_KEYS = tuple(_PROFILE_ALIASES.values())


def fetch_user_profile_fields(account_id, table_name="UserData_PlungePals") -> dict:
    """Query ``accountId-index`` for the fields the calorie model needs.

    Returns ``{}`` on any error or empty result. Never raises. Caches the
    DynamoDB resource handle on first use so warm Lambda invocations reuse it.
    """
    global _dynamodb
    try:
        if account_id is None or str(account_id).strip() == "":
            return {}

        if _dynamodb is None:
            import boto3  # noqa: PLC0415 — lazy so tests need no boto3

            _dynamodb = boto3.resource("dynamodb")

        from boto3.dynamodb.conditions import Key  # noqa: PLC0415

        table = _dynamodb.Table(table_name)
        response = table.query(
            IndexName="accountId-index",
            KeyConditionExpression=Key("accountId").eq(account_id),
            ProjectionExpression="#uh, #uw, #g, #dob, #uom, #prem",
            ExpressionAttributeNames=dict(_PROFILE_ALIASES),
            Limit=1,
        )
        items = response.get("Items") or []
        if not items:
            return {}

        item = items[0]
        return {key: item[key] for key in _PROFILE_KEYS if key in item}
    except Exception:
        logger.warning("fetch_user_profile_fields failed; returning empty dict", exc_info=True)
        return {}
