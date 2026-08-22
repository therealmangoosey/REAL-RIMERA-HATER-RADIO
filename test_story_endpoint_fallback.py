import unittest

from story_endpoint_fallback import StoryEndpointFallback


class TestStoryEndpointFallback(unittest.TestCase):
    def test_provider_page_img_is_never_story_media(self):
        response = type("Response", (), {
            "text": '<html><img src="https://ensaver.net/images/logo.png"></html>',
            "url": "https://ensaver.net/instagram-story-downloader",
            "json": lambda self: (_ for _ in ()).throw(ValueError("not json")),
        })()
        candidates = StoryEndpointFallback._extract_candidates(
            response, "3968959993327947725", trusted_result=True
        )
        self.assertEqual(candidates, [])

    def test_trusted_video_link_can_be_extracted_without_story_id(self):
        response = type("Response", (), {
            "text": '<a href="https://cdn.example.net/a8f3c1.mp4">Download</a>',
            "url": "https://ensaver.net/result",
            "json": lambda self: (_ for _ in ()).throw(ValueError("not json")),
        })()
        candidates = StoryEndpointFallback._extract_candidates(
            response, "3968959993327947725", trusted_result=True
        )
        self.assertEqual(candidates, ["https://cdn.example.net/a8f3c1.mp4"])


if __name__ == "__main__":
    unittest.main()
