import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from instagram_fallback import InstagramPublicFallback
from media_downloader import MediaDownloader


class TestMediaDownloader(unittest.TestCase):
    def test_default_max_bytes_is_set(self):
        downloader = MediaDownloader()
        self.assertEqual(downloader.max_bytes, 20 * 1024 * 1024)

    def test_extract_urls_strips_punctuation(self):
        downloader = MediaDownloader()
        urls = downloader.extract_urls("See https://example.com/video).")
        self.assertEqual(urls, ["https://example.com/video"])

    def test_instagram_url_detection(self):
        downloader = MediaDownloader()
        self.assertTrue(downloader._is_instagram_story("https://www.instagram.com/stories/user/123/"))
        self.assertTrue(downloader._instagram_post_or_reel("https://www.instagram.com/p/ABC/"))
        self.assertTrue(downloader._instagram_post_or_reel("https://www.instagram.com/reel/ABC/"))
        self.assertFalse(downloader._instagram_post_or_reel("https://www.tiktok.com/@user/video/123"))

    @patch("media_downloader.parth_dl.download")
    def test_parth_dl_fallback_returns_carousel_files(self, mock_download):
        with TemporaryDirectory() as temp_dir:
            first = os.path.join(temp_dir, "slide_01.jpg")
            second = os.path.join(temp_dir, "slide_02.jpg")
            with open(first, "wb") as handle:
                handle.write(b"x" * 5000)
            with open(second, "wb") as handle:
                handle.write(b"y" * 5000)
            mock_download.return_value = [first, second]

            downloader = MediaDownloader()
            result = downloader._parth_dl_fallback(
                "https://www.instagram.com/p/DbG-2cqkU3F/",
                temp_dir,
            )

            self.assertEqual(result, [first, second])
            mock_download.assert_called_once_with(
                "https://www.instagram.com/p/DbG-2cqkU3F/",
                output_path=temp_dir,
                quality="best",
                verbose=False,
            )


class TestInstagramFallback(unittest.TestCase):
    def test_service_page_image_is_not_treated_as_media_url(self):
        self.assertFalse(
            InstagramPublicFallback._looks_like_media_url(
                "https://www.instaloadr.com/static/assets/download-button.png"
            )
        )
        self.assertFalse(
            InstagramPublicFallback._looks_like_media_url(
                "https://play.google.com/store/apps/details?id=example"
            )
        )
        self.assertFalse(
            InstagramPublicFallback._looks_like_media_url(
                "https://www.instagram.com/static/images/Instagram-icon.png"
            )
        )

    def test_cdn_media_url_is_accepted(self):
        self.assertTrue(
            InstagramPublicFallback._looks_like_media_url(
                "https://scontent.cdninstagram.com/v/t51.2885-15/123.jpg"
            )
        )

    def test_structured_resolver_extracts_media_urls_from_json(self):
        payload = {
            "media": [
                {"download_url": "https://scontent.cdninstagram.com/v/t51.2885-15/123.jpg"},
                {"url": "https://scontent.cdninstagram.com/v/t51.2885-15/456.mp4"},
            ]
        }
        urls = InstagramPublicFallback._extract_urls_from_json(payload)
        self.assertEqual(
            urls,
            [
                "https://scontent.cdninstagram.com/v/t51.2885-15/123.jpg",
                "https://scontent.cdninstagram.com/v/t51.2885-15/456.mp4",
            ],
        )

    def test_download_candidates_rejects_html(self):
        fallback = InstagramPublicFallback()
        response = Mock()
        response.status_code = 200
        response.url = "https://example.com/result"
        response.headers = {"content-type": "text/html; charset=utf-8"}
        response.raise_for_status.return_value = None
        fallback.session.get = Mock(return_value=response)

        with TemporaryDirectory() as temp_dir:
            files = fallback._download_candidates(["https://example.com/result"], temp_dir, "test")
            self.assertEqual(files, [])
            self.assertEqual(os.listdir(temp_dir), [])


if __name__ == "__main__":
    unittest.main()
