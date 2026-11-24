import unittest

from pydantic import ValidationError

from app.schemas.address import AddressUpdate


class AddressUpdateTests(unittest.TestCase):
    def test_omitted_fields_are_not_changed(self):
        self.assertEqual(AddressUpdate().model_dump(exclude_unset=True), {})

    def test_nullable_fields_can_be_cleared(self):
        patch = AddressUpdate(line2=None, landmark=None)
        self.assertEqual(
            patch.model_dump(exclude_unset=True),
            {"line2": None, "landmark": None},
        )

    def test_required_fields_reject_explicit_null(self):
        for field in ("full_name", "phone", "line1", "city", "state", "pincode", "is_default"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    AddressUpdate.model_validate({field: None})

    def test_blank_required_fields_are_rejected(self):
        for field in ("full_name", "phone", "line1", "city", "state", "pincode"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    AddressUpdate.model_validate({field: "   "})

    def test_patch_values_are_trimmed(self):
        patch = AddressUpdate(full_name="  Example Customer  ", line2="  Flat 2  ")
        self.assertEqual(
            patch.model_dump(exclude_unset=True),
            {"full_name": "Example Customer", "line2": "Flat 2"},
        )


if __name__ == "__main__":
    unittest.main()
