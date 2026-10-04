import json
import unittest

from gate import ContractError, validate


INVOICE = {
    "type": "object",
    "fields": {
        "vendor": {"type": "string", "max_length": 100},
        "total": {"type": "number", "min": 0},
        "currency": {"type": "string", "choices": ["EUR", "USD"]},
    },
    "required": ["vendor", "total", "currency"],
}


class GateTests(unittest.TestCase):
    def test_large_integer_bound_does_not_overflow_float_conversion(self):
        self.assertEqual(validate('1', {'type': 'integer', 'max': 10 ** 400}), 1)

    def test_accepts_valid_invoice_without_changing_values(self):
        text = '{"vendor":"Example GmbH","total":42.5,"currency":"EUR"}'
        self.assertEqual(validate(text, INVOICE), {"vendor": "Example GmbH", "total": 42.5, "currency": "EUR"})

    def test_rejects_missing_required_field(self):
        with self.assertRaises(ContractError):
            validate('{"vendor":"A","total":1}', INVOICE)

    def test_rejects_unknown_fields_without_echoing_content(self):
        with self.assertRaises(ContractError) as caught:
            validate('{"vendor":"A","total":1,"currency":"EUR","private-secret":1}', INVOICE)
        self.assertNotIn("private-secret", str(caught.exception))

    def test_boolean_is_not_number(self):
        with self.assertRaises(ContractError):
            validate('true', {"type": "number"})

    def test_boolean_is_not_integer(self):
        with self.assertRaises(ContractError):
            validate('false', {"type": "integer"})

    def test_rejects_duplicate_keys(self):
        with self.assertRaises(ContractError):
            validate('{"x":1,"x":2}', {"type": "object", "fields": {"x": {"type": "integer"}}})

    def test_rejects_nonfinite_and_overflow_numbers(self):
        for text in ['NaN', 'Infinity', '-Infinity', '1e999']:
            with self.subTest(text=text), self.assertRaises(ContractError):
                validate(text, {"type": "number"})

    def test_does_not_extract_json_from_prose_or_markdown(self):
        for text in ['Here is the answer: 4', '```json\n4\n```', '4 5']:
            with self.subTest(text=text), self.assertRaises(ContractError):
                validate(text, {"type": "integer"})

    def test_enforces_utf8_byte_budget(self):
        with self.assertRaises(ContractError):
            validate('"ää"', {"type": "string"}, max_bytes=5)

    def test_enforces_nesting_budget(self):
        with self.assertRaises(ContractError):
            validate('[[[1]]]', {"type": "array", "items": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}}}, max_depth=2)

    def test_checks_nested_array_items(self):
        contract = {"type": "array", "items": {"type": "integer"}, "max_length": 3}
        self.assertEqual(validate('[1,2]', contract), [1, 2])
        with self.assertRaises(ContractError):
            validate('[1,"2"]', contract)

    def test_bounds_strings_and_arrays(self):
        for text, contract in [('"long"', {"type": "string", "max_length": 3}), ('[1,2]', {"type": "array", "items": {"type": "integer"}, "max_length": 1})]:
            with self.subTest(text=text), self.assertRaises(ContractError):
                validate(text, contract)

    def test_numeric_bounds_and_choices(self):
        for text, contract in [('0', {"type": "number", "min": 1}), ('3', {"type": "integer", "max": 2}), ('"GBP"', {"type": "string", "choices": ["EUR"]})]:
            with self.subTest(text=text), self.assertRaises(ContractError):
                validate(text, contract)

    def test_rejects_unknown_or_malformed_contract_rules(self):
        for contract in [{"type": "number", "minimum": 1}, {"type": "oops"}, {"type": "object", "fields": {}, "required": ["missing"]}, {"type": "array"}, {"type": "string", "max_length": -1}, {"type": "number", "min": 5, "max": 1}, {"type": "string", "choices": []}]:
            with self.subTest(contract=contract), self.assertRaises(ContractError):
                validate('null', contract)

    def test_no_type_coercion(self):
        with self.assertRaises(ContractError):
            validate('"42"', {"type": "number"})

    def test_supports_explicit_null_and_boolean(self):
        self.assertIsNone(validate('null', {"type": "null"}))
        self.assertIs(validate('true', {"type": "boolean"}), True)

    def test_optional_fields_are_still_validated(self):
        contract = {"type": "object", "fields": {"x": {"type": "integer"}}}
        self.assertEqual(validate('{}', contract), {})
        with self.assertRaises(ContractError):
            validate('{"x":"bad"}', contract)

    def test_invalid_unicode_and_extreme_depth_fail_cleanly(self):
        for text in ['"\ud800"', '[' * 1100 + '0' + ']' * 1100]:
            with self.subTest(size=len(text)), self.assertRaises(ContractError):
                validate(text, {"type": "string"})


if __name__ == "__main__":
    unittest.main()
