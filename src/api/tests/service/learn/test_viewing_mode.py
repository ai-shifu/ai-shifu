import unittest

from flaskr.service.learn.learn_dtos import ViewingModeDTO
from flaskr.service.learn.viewing_mode import build_viewing_mode_prompt


class ViewingModePromptTests(unittest.TestCase):
    def test_build_viewing_mode_prompt_returns_none_when_missing(self):
        self.assertIsNone(build_viewing_mode_prompt(None))

    def test_build_viewing_mode_prompt_formats_template(self):
        prompt = build_viewing_mode_prompt(
            ViewingModeDTO(
                container_size="358*608px",
                device_type="mobile",
            )
        )

        self.assertIn("358*608px", prompt)
        self.assertIn("移动端", prompt)
        self.assertIn("text-base", prompt)
        self.assertIn("16:9", prompt)

    def test_viewing_mode_dto_normalizes_device_type(self):
        viewing_mode = ViewingModeDTO(
            container_size="390*844px",
            device_type="MOBILE",
        )

        self.assertEqual(viewing_mode.device_type, "mobile")

    def test_viewing_mode_dto_rejects_invalid_container_size(self):
        with self.assertRaises(ValueError):
            ViewingModeDTO(
                container_size="390x844",
                device_type="mobile",
            )

    def test_viewing_mode_dto_rejects_tablet_device_type(self):
        with self.assertRaises(ValueError):
            ViewingModeDTO(
                container_size="834*1112px",
                device_type="tablet",
            )
