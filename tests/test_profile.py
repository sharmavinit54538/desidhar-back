import unittest

from pydantic import ValidationError

from app.schemas.auth import UserUpdate


class ProfileInputTests(unittest.TestCase):
    def test_profile_fields_are_trimmed(self):
        profile = UserUpdate(full_name="  Vinit Sharma  ", phone=" 9876543210 ")
        self.assertEqual(
            profile.model_dump(exclude_unset=True),
            {"full_name": "Vinit Sharma", "phone": "9876543210"},
        )

    def test_partial_updates_preserve_unsupplied_fields(self):
        self.assertEqual(UserUpdate(phone="9876543210").model_dump(exclude_unset=True), {"phone": "9876543210"})
        self.assertEqual(UserUpdate().model_dump(exclude_unset=True), {})

    def test_optional_profile_fields_can_be_cleared(self):
        self.assertEqual(UserUpdate(full_name=None).model_dump(exclude_unset=True), {"full_name": None})
        self.assertEqual(UserUpdate(phone=None).model_dump(exclude_unset=True), {"phone": None})

    def test_rejects_invalid_profile_fields(self):
        for payload in (
            {"full_name": "   "},
            {"full_name": "x" * 101},
            {"phone": "1234567890"},
            {"phone": "987654321"},
            {"phone": "98765432100"},
            {"phone": "987654321x"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                UserUpdate(**payload)

    def test_identity_and_privilege_fields_cannot_be_updated(self):
        for payload in ({"email": "other@example.com"}, {"role": "admin"}, {"is_active": False}, {"id": "other-user"}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                UserUpdate(**payload)


if __name__ == "__main__":
    unittest.main()
