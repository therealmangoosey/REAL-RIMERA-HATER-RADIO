from unittest import TestCase

from story_endpoint_fallback import StoryEndpointFallback


class TestStoryEndpointFallback(TestCase):
    def test_plain_media_filename_is_allowed_only_for_trusted_result(self):
        response = type("R", (), {
            "url": "https://provider.example/result",
            "text": '<a href="https://cdn.example/files/abc123.mp4">Download</a>',
        })()
        self.assertEqual(
            StoryEndpointFallback._extract_candidates(response, "3968959993327947725", trusted_result=True),
            ["https://cdn.example/files/abc123.mp4"],
        )

    def test_generic_provider_assets_are_not_accepted(self):
        response = type("R", (), {
            "url": "https://provider.example/result",
            "text": '<img src="https://provider.example/assets/logo.png"><img src="https://provider.example/thumb.jpg">',
        })()
        self.assertEqual(
            StoryEndpointFallback._extract_candidates(response, "3968959993327947725", trusted_result=True),
            [],
        )
