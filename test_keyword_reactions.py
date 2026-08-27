import json
import os
import tempfile
import unittest
from unittest.mock import patch

from keyword_reactions import matching_reactions, reactions_enabled, set_reactions_enabled


class TestKeywordReactions(unittest.TestCase):
    def test_case_insensitive_manual_aliases(self):
        self.assertEqual(
            matching_reactions("JAZZ PUNK bushwa Vol 1 VOLUME TWO"),
            [
                "<:JazzPunk:1395637360682602587>",
                "<:BUSHWA:1395637306408566805>",
                "<:CatchMeIfYouCan:1480703883356536985>",
                "<:RealRimeraHaterRadio:1504949135655305246>",
            ],
        )

    def test_all_manual_aliases(self):
        content = (
            "jazz punk bushwa vol 1 volume one vol 2 volume 2 volume two "
            "real rimera hater real rimera hater radio rimera cd dense cw campwander"
        )
        self.assertEqual(
            matching_reactions(content),
            [
                "<:JazzPunk:1395637360682602587>",
                "<:BUSHWA:1395637306408566805>",
                "<:CatchMeIfYouCan:1480703883356536985>",
                "<:RealRimeraHaterRadio:1504949135655305246>",
                "<:Pinkface:1430050553752190996>",
                "<:TheCDKeeper:1482891305171554304>",
                "<:dense:1512748563648479342>",
                "<:CAMPWANDER:1492324641556008970>",
            ],
        )

    def test_multiple_matches_get_each_unique_emoji(self):
        self.assertEqual(
            matching_reactions("rimera CD Rimera campwander CW"),
            [
                "<:Pinkface:1430050553752190996>",
                "<:TheCDKeeper:1482891305171554304>",
                "<:CAMPWANDER:1492324641556008970>",
            ],
        )

    def test_aliases_are_whole_phrases(self):
        self.assertEqual(matching_reactions("rimerarimera cdense campwanderx"), [])

    def test_empty_content(self):
        self.assertEqual(matching_reactions(""), [])

    def test_toggle_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "config.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump({"polling_interval_minutes": 5}, handle)

            with patch("keyword_reactions.CONFIG_FILE", config_path):
                self.assertTrue(set_reactions_enabled(False))
                self.assertFalse(reactions_enabled())

                with open(config_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertFalse(saved["reactions_enabled"])

                self.assertTrue(set_reactions_enabled(True))
                self.assertTrue(reactions_enabled())

                with open(config_path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertTrue(saved["reactions_enabled"])


if __name__ == "__main__":
    unittest.main()
