import unittest

from story_endpoint_fallback import StoryEndpointFallback


class TestEmbeddedStoryExtraction(unittest.TestCase):
    def test_extracts_story_id_tied_cdn_video_from_embedded_json(self):
        story_id = "3968891156947555281"
        media_url = "https://scontent.cdninstagram.com/v/t51.2885-15/story.mp4"
        html = (
            '<script>window.__DATA__={"story_id":"3968891156947555281",'
            f'"video_versions":[{{"url":"{media_url}"}}]}};</script>'
        )
        self.assertEqual(
            StoryEndpointFallback._embedded_story_urls(html, story_id),
            [media_url],
        )

    def test_does_not_accept_unrelated_cdn_media_without_story_context(self):
        story_id = "3968891156947555281"
        unrelated = "https://scontent.cdninstagram.com/v/t51.2885-15/post.mp4"
        html = f'<script>var image="{unrelated}";</script>'
        self.assertEqual(
            StoryEndpointFallback._embedded_story_urls(html, story_id),
            [],
        )

    def test_extracts_story_media_from_data_attribute(self):
        story_id = "3968891156947555281"
        media_url = "https://media.example.invalid/story-no-extension"
        html = (
            f'<div data-story-id="{story_id}" '
            f'data-video="{media_url}"></div>'
        )
        self.assertEqual(
            StoryEndpointFallback._embedded_story_urls(html, story_id),
            [media_url],
        )


if __name__ == "__main__":
    unittest.main()
