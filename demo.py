"""Run a synthetic invoice through accepted and rejected response paths."""
import json

from gate import ContractError, validate

CONTRACT = {
    "type": "object",
    "fields": {
        "vendor": {"type": "string", "max_length": 100},
        "total": {"type": "number", "min": 0},
        "currency": {"type": "string", "choices": ["EUR", "USD"]},
    },
    "required": ["vendor", "total", "currency"],
}

for name, response in [
    ("valid extraction", '{"vendor":"Demo Supplies","total":42.5,"currency":"EUR"}'),
    ("wrong type", '{"vendor":"Demo Supplies","total":"42.5","currency":"EUR"}'),
    ("unexpected action", '{"vendor":"Demo Supplies","total":42.5,"currency":"EUR","execute":"pay"}'),
]:
    try:
        result = validate(response, CONTRACT)
        print(json.dumps({"case": name, "accepted": True, "data": result}))
    except ContractError as error:
        print(json.dumps({"case": name, "accepted": False, "reason": str(error)}))
