"""输入框文字/背景分类回归测试，无需 TIM 原始资源。"""
import pathlib
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import gmdark
import gmdscan
import td


def record(name, value):
    return (td.encode_record("TD", 1, 0x0b, name.encode("ascii"))
            + struct.pack("<II", 4, value))


class InputFrameTests(unittest.TestCase):
    def patch(self, filename, properties):
        original = b"".join(record(name, value) for name, value in properties.items())
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / "inputframe" / filename
            path.parent.mkdir()
            path.write_bytes(original)
            preview = gmdark.patch_file(str(path), dry=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(gmdark.patch_file(str(path)), preview)
            result = path.read_bytes()
            self.assertEqual(len(result), len(original))
        return {r["text"]: struct.unpack("<I", r["value"])[0]
                for r in gmdscan.scan(result) if r["value"] and len(r["value"]) == 4}

    def test_text_white_background_dark(self):
        result = self.patch("InputFrame.gmd", {
            "textColor": 0xFF000000, "normalColor": 0xFF333333,
            "clrText": 0x00000000, "color": 0xFF000000,
            "backgroundColor": 0xFFFFFFFF, "borderColor": 0xFFCCCCCC,
            "maskColor": 0xFF000000,
        })
        for name in ("textColor", "normalColor", "color"):
            self.assertEqual(result[name], 0xFFFFFFFF)
        self.assertEqual(result["clrText"], 0x00FFFFFF)
        self.assertEqual(result["backgroundColor"], 0xFF141414)
        self.assertEqual(result["borderColor"], 0xFF202020)
        self.assertEqual(result["maskColor"], 0xFF000000)

    def test_auto_color_keeps_dark_brightness_input(self):
        result = self.patch("InputFrame_AutoColor.gmd", {"color": 0xFFFFFFFF})
        self.assertEqual(result["color"], 0xFF141414)


if __name__ == "__main__":
    unittest.main()
