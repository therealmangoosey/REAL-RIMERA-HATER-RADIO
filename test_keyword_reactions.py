import unittest

from keyword_reactions import matching_reactions


class TestKeywordReactions(unittest.TestCase):
    def test_case_and_punctuation(self):
        self.assertEqual(matching_reactions("Rimera! MUSIC, merch."), ["💗", "🎶", "🛍️"])

    def test_keywords_are_whole_words(self):
        self.assertEqual(matching_reactions("rimerahater rimera"), ["😭", "💗"])
        self.assertEqual(matching_reactions("rimerarimera"), [])

    def test_empty_content(self):
        self.assertEqual(matching_reactions(""), [])

    def test_caps_reaction_count(self):
        self.assertLessEqual(len(matching_reactions("rimera music merch instagram spotify youtube")), 3)


if __name__ == "__main__":
    unittest.main()
