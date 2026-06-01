"""Library locator unit tests.

Run from the repo root with:
python -m unittest discover -s tests -p "test_*.py"
"""

import unittest

from library import (
    LOCATOR_NAME_MAX_LENGTH,
    deduplicate_export_locator_names,
    sanitize_export_locator_name,
)


class SanitizeExportLocatorNameTests(unittest.TestCase):
    def test_core_cases_match_existing_selfcheck(self):
        cases = [
            ("   ", "locator"),
            ("rig:locator", "rig_locator"),
            ("root|locator", "root_locator"),
            ("漢字", "locator"),
            ("1locator", "locator_1locator"),
            ("  ns:bébé|ctrl  ", "ns_bébé_ctrl"),
        ]

        for original_name, expected_name in cases:
            with self.subTest(original_name=original_name):
                self.assertEqual(
                    sanitize_export_locator_name(original_name),
                    expected_name,
                )

    def test_truncates_to_locator_max_length(self):
        long_name = "A" * 80

        sanitized_name = sanitize_export_locator_name(long_name)

        self.assertEqual(sanitized_name, "A" * LOCATOR_NAME_MAX_LENGTH)
        self.assertEqual(len(sanitized_name), LOCATOR_NAME_MAX_LENGTH)


class DeduplicateExportLocatorNamesTests(unittest.TestCase):
    def test_unicode_names_fall_back_and_suffix(self):
        self.assertEqual(
            deduplicate_export_locator_names(["漢字", "漢字"]),
            ["locator", "locator-001"],
        )

    def test_duplicate_long_names_keep_suffix_within_max_length(self):
        long_name = "A" * 80
        expected_second_name = (
            "A" * (LOCATOR_NAME_MAX_LENGTH - len("-001")) + "-001"
        )

        deduplicated_names = deduplicate_export_locator_names(
            [long_name, long_name]
        )

        self.assertEqual(
            deduplicated_names[0],
            "A" * LOCATOR_NAME_MAX_LENGTH,
        )
        self.assertEqual(deduplicated_names[1], expected_second_name)

    def test_mixed_duplicates_increment_suffixes_deterministically(self):
        self.assertEqual(
            deduplicate_export_locator_names(
                ["rig:locator", "rig_locator", "rig locator", "rig_locator"]
            ),
            [
                "rig_locator",
                "rig_locator-001",
                "rig_locator-002",
                "rig_locator-003",
            ],
        )


if __name__ == "__main__":
    unittest.main()

