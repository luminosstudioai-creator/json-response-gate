"""Strict, offline contracts for model responses. No repair and no execution."""

import json
import math


class ContractError(ValueError):
    """Invalid contract or response; messages never include response values."""


def _matches(value, kind):
    return {
        "string": type(value) is str,
        "integer": type(value) is int,
        "number": type(value) in (int, float),
        "boolean": type(value) is bool,
        "null": value is None,
        "object": type(value) is dict,
        "array": type(value) is list,
    }.get(kind, False)


def _schema(contract, depth=0):
    if depth > 20 or type(contract) is not dict:
        raise ContractError("invalid contract")
    kind = contract.get("type")
    rules = {
        "string": {"max_length", "choices"},
        "integer": {"min", "max", "choices"},
        "number": {"min", "max", "choices"},
        "boolean": {"choices"}, "null": set(),
        "object": {"fields", "required"}, "array": {"items", "max_length"},
    }
    if type(kind) is not str or kind not in rules or set(contract) - (rules[kind] | {"type"}):
        raise ContractError("unknown contract rule")
    if "max_length" in contract and (type(contract["max_length"]) is not int or contract["max_length"] < 0):
        raise ContractError("invalid length limit")
    for bound in ("min", "max"):
        if bound in contract and (type(contract[bound]) not in (int, float) or (type(contract[bound]) is float and not math.isfinite(contract[bound]))):
            raise ContractError("invalid numeric bound")
    if "min" in contract and "max" in contract and contract["min"] > contract["max"]:
        raise ContractError("inverted bounds")
    if "choices" in contract:
        choices = contract["choices"]
        if type(choices) is not list or not choices or any(not _matches(v, kind) for v in choices):
            raise ContractError("invalid choices")
        if any(type(v) is float and not math.isfinite(v) for v in choices):
            raise ContractError("invalid choices")
    if kind == "object":
        fields = contract.get("fields")
        required = contract.get("required", [])
        if type(fields) is not dict or any(type(k) is not str for k in fields):
            raise ContractError("invalid fields")
        if type(required) is not list or any(type(k) is not str or k not in fields for k in required):
            raise ContractError("invalid required fields")
        for rule in fields.values():
            _schema(rule, depth + 1)
    if kind == "array":
        _schema(contract.get("items"), depth + 1)


def _check(value, contract, path="$", depth=0, max_depth=20):
    if depth > max_depth:
        raise ContractError("response nesting limit exceeded")
    kind = contract["type"]
    if not _matches(value, kind):
        raise ContractError(f"{path}: wrong type")
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise ContractError(f"{path}: invalid Unicode") from None
    if type(value) is float and not math.isfinite(value):
        raise ContractError(f"{path}: non-finite number")
    if "choices" in contract and value not in contract["choices"]:
        raise ContractError(f"{path}: disallowed choice")
    if "max_length" in contract and len(value) > contract["max_length"]:
        raise ContractError(f"{path}: length limit exceeded")
    if "min" in contract and value < contract["min"]:
        raise ContractError(f"{path}: below minimum")
    if "max" in contract and value > contract["max"]:
        raise ContractError(f"{path}: above maximum")
    if kind == "object":
        fields = contract["fields"]
        if set(value) - set(fields):
            raise ContractError(f"{path}: unknown field")
        if set(contract.get("required", [])) - set(value):
            raise ContractError(f"{path}: missing required field")
        for key, item in value.items():
            _check(item, fields[key], f"{path}.{key}", depth + 1, max_depth)
    if kind == "array":
        for index, item in enumerate(value):
            _check(item, contract["items"], f"{path}[{index}]", depth + 1, max_depth)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate object key")
        result[key] = value
    return result


def _reject_constant(_):
    raise ContractError("non-finite JSON constant")


def validate(text, contract, *, max_bytes=65536, max_depth=20):
    """Return parsed JSON only if it satisfies the complete custom contract.

    Contracts are trusted application configuration, not model-produced input.
    Objects reject extra fields. This is intentionally not JSON Schema.
    """
    if type(max_bytes) is not int or max_bytes < 1 or type(max_depth) is not int or not 1 <= max_depth <= 100:
        raise ContractError("invalid resource limits")
    _schema(contract)
    if type(text) is not str:
        raise ContractError("response must be text")
    try:
        if len(text.encode("utf-8")) > max_bytes:
            raise ContractError("response byte limit exceeded")
    except UnicodeError:
        raise ContractError("invalid Unicode") from None
    # Bound nesting before the recursive JSON parser; quoted brackets are data.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                raise ContractError("response nesting limit exceeded")
        elif char in "]}":
            depth -= 1
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise ContractError("invalid JSON response") from None
    _check(value, contract, max_depth=max_depth)
    return value
