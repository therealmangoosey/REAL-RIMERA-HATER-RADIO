import unittest
from unittest.mock import Mock, patch

from media_downloader import MediaDownloader


class TestPublicStoryOrder(unittest.TestCase):
    @patch.object(MediaDownloader, "_extract")
    @patch.object(MediaDownloader, "_download_story_public_first")
    def test_public_story_uses_public_fallback_before_ytdlp(self, mock_public, mock_extract):
        downloader = MediaDownloader()
        mock_public.return_value = (["/tmp/story.mp4"], "public Story endpoint fallback")

        workdir = "/tmp/rimera-test"
        with patch("media_downloader.tempfile.mkdtemp", return_value=workdir), patch(
            "media_downloader.shutil.rmtree"
        ):
            result = downloader.download("https://www.instagram.com/stories/rimeraera/123/")

        self.assertEqual(result[0], workdir)
        self.assertEqual(result[1], ["/tmp/story.mp4"])
        self.assertEqual(result[2]["source"], "public Story endpoint fallback")
        mock_public.assert_called_once()
        mock_extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
