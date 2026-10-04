"""用合成字节检查独立补丁的修改范围和拒绝条件，不含 TIM 文件。"""
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import patch_input
import patch_paste_path


class OptionalPatchTests(unittest.TestCase):
    def test_input_changes_only_site_and_cave(self):
        original = bytes(16) + patch_input.ORIGINAL + bytes(226)
        body = bytes.fromhex("8b5424089cf7c2ffffff007505baffffff009d8d8114010000c3")
        with patch.object(patch_input, "layout", return_value=(16, 64, b"P" * 10, body)):
            result = patch_input.patch_bytes(original)
            self.assertEqual(len(result), len(original))
            self.assertEqual(result[:16], original[:16])
            self.assertEqual(result[26:64], original[26:64])
            self.assertEqual(result[64 + len(body):], original[64 + len(body):])
            self.assertEqual(result[16:26], b"P" * 10)
            self.assertEqual(result[64:64 + len(body)], body)
            with self.assertRaises(ValueError):
                patch_input.patch_bytes(result)

    def test_paste_embeds_path_without_changing_length(self):
        original = bytes(16) + patch_paste_path.ORIGINAL + bytes(488)
        with patch.object(patch_paste_path, "layout", return_value=(16, 64, 0x200000, 448)):
            result = patch_paste_path.build(original, r"D:\Data")
            encoded = ("D:\\Data\0").encode("utf-16-le")
            end = 64 + 38 + len(encoded)
            self.assertEqual(len(result), len(original))
            self.assertEqual(result[102:end], encoded)
            self.assertEqual(result[:16], original[:16])
            self.assertEqual(result[24:64], original[24:64])
            self.assertEqual(result[end:], original[end:])
            with self.assertRaises(ValueError):
                patch_paste_path.build(result, r"D:\Data")

    def test_paste_rejects_long_path_and_occupied_cave(self):
        original = bytes(16) + patch_paste_path.ORIGINAL + bytes(488)
        with patch.object(patch_paste_path, "layout", return_value=(16, 64, 0x200000, 448)):
            for data, directory in ((original, "a" * 260),
                                    (original[:64] + b"x" + original[65:], "D:\\Data")):
                with self.assertRaises(ValueError):
                    patch_paste_path.build(data, directory)


if __name__ == "__main__":
    unittest.main()
