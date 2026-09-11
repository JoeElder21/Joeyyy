"""The terminal's stdlib schema validator and the document schemas it enforces."""

import unittest

from terminal import schema


class ValidatorTests(unittest.TestCase):
    def test_type_required_and_additional_properties(self):
        spec = {
            "type": "object",
            "required": ["a"],
            "properties": {"a": {"type": "integer"}, "b": {"type": ["string", "null"]}},
            "additionalProperties": False,
        }
        self.assertEqual(schema.validate({"a": 1, "b": None}, spec), [])
        errors = schema.validate({"b": 2, "c": 3}, spec)
        self.assertTrue(any("missing required property 'a'" in e for e in errors))
        self.assertTrue(any("$.b: expected type" in e for e in errors))
        self.assertTrue(any("unexpected property 'c'" in e for e in errors))

    def test_booleans_are_not_numbers(self):
        self.assertTrue(schema.validate(True, {"type": "number"}))
        self.assertTrue(schema.validate(True, {"type": "integer"}))
        self.assertEqual(schema.validate(2, {"type": "number", "minimum": 2}), [])

    def test_enum_const_pattern_and_bounds(self):
        self.assertTrue(schema.validate("x", {"enum": ["a", "b"]}))
        self.assertTrue(schema.validate("x", {"const": "y"}))
        self.assertTrue(schema.validate("abc", {"pattern": "^[0-9]+$"}))
        self.assertTrue(schema.validate(5, {"exclusiveMaximum": 5}))
        self.assertTrue(schema.validate([1, 2, 3], {"maxItems": 2}))
        self.assertTrue(schema.validate("ab", {"minLength": 3}))

    def test_items_anyof_oneof_and_local_ref(self):
        spec = {
            "definitions": {"pos": {"type": "number", "exclusiveMinimum": 0}},
            "type": "array",
            "items": {"anyOf": [{"$ref": "#/definitions/pos"}, {"type": "null"}]},
        }
        self.assertEqual(schema.validate([1, None, 2.5], spec), [])
        self.assertTrue(schema.validate([0], spec))
        self.assertTrue(schema.validate("a", {"oneOf": [{"type": "string"}, {"minLength": 1}]}))

    def test_unsupported_keyword_is_an_error_not_a_pass(self):
        with self.assertRaises(schema.SchemaError):
            schema.validate({}, {"type": "object", "patternProperties": {}})
        with self.assertRaises(schema.SchemaError):
            schema.validate(1, {"$ref": "http://elsewhere/schema"})

    def test_require_raises_with_the_schema_name(self):
        with self.assertRaises(schema.SchemaError) as ctx:
            schema.require({}, "policy")
        self.assertIn("policy:", str(ctx.exception))


class DocumentSchemaTests(unittest.TestCase):
    EXPECTED = {
        "board",
        "evidence",
        "health",
        "learning",
        "outcome",
        "policy",
        "portfolio_state",
        "recommendation",
        "research_run",
        "security_research",
        "snapshot",
    }

    def test_every_expected_schema_is_present(self):
        self.assertEqual(set(schema.schema_names()), self.EXPECTED)

    def test_every_schema_uses_only_supported_keywords(self):
        for name in schema.schema_names():
            with self.subTest(schema=name):
                errors = schema.validate({}, schema.load_schema(name))
                self.assertTrue(errors, f"{name} accepted an empty object")


if __name__ == "__main__":
    unittest.main()
