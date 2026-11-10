import unittest

import support  # noqa: F401  (puts part1/pipeline on sys.path)
from mappers import MAPPERS
from model import TABLE_COLUMNS

EXPECTED = {"amazon", "brand_site_and_emails", "google_ads_transparency", "google_results", "meta_ad_library",
            "retail_shelf", "search_interest", "tiktok_ads", "tiktok_posts", "tiktok_shop"}


class RegistryTest(unittest.TestCase):
    def test_all_ten_mappers_are_registered_under_their_source(self):
        self.assertEqual(set(MAPPERS), EXPECTED)
        for key, mapper in MAPPERS.items():
            self.assertEqual(mapper.SOURCE, key)

    def test_every_mapper_has_a_valid_contract(self):
        for key, mapper in MAPPERS.items():
            with self.subTest(source=key):
                self.assertTrue(callable(mapper.map_run))
                for (table, kind), policy in mapper.ENDING.items():
                    self.assertIn(table, TABLE_COLUMNS)
                    self.assertIsInstance(kind, str)
                    self.assertIn(policy, ("absent", "source_date", "never"))
