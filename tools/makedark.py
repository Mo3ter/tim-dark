#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 TIM 的 appframework/config/theme.xml 改成深色调色板 + 白字。

原则（用户要求）：在我们造出来的深色底上，**每一个可读字符串都必须是纯白 (#FFFFFF)**。
只有真正明亮的强调色 —— 链接蓝、警告红/橙 —— 保留色相，这样链接还能看出来。
表面色一律用下面的深色调色板。

Usage: python makedark.py <theme.xml> [--revert]
"""
import io
import re
import shutil
import sys

WHITE = "0xffffff"

# (组名, 变量名) -> 新值。组名为 None 表示任意组。
EXPLICIT = {
    # ---- TIMColor：TIM 外壳的表面调色板 ------------------------------------
    ("TIMColor", "WindowBackground"): "0x1a1a1a",
    ("TIMColor", "MainLeft"): "0x2a2a2a",
    ("TIMColor", "MainRight"): "0x1f1f1f",
    ("TIMColor", "MainRightContent"): "0x1f1f1f",
    ("TIMColor", "SplitLineInGray"): "0x1affffff",
    ("TIMColor", "SplitLineInWhite"): "0x3a3a3a",
    ("TIMColor", "HoverItemInGray"): "0x1affffff",
    ("TIMColor", "PressItemInGray"): "0x26ffffff",
    ("TIMColor", "HoverItemInWhite"): "0x2f2f2f",
    ("TIMColor", "PressItemInWhite"): "0x383838",
    ("TIMColor", "SplitItemInWhite"): "0x2f2f2f",
    ("TIMColor", "GrayBkg"): "0x2a2a2a",
    ("TIMColor", "HoverGrayBkg"): "0x333333",
    ("TIMColor", "PushedGrayBkg"): "0x3c3c3c",
    # 文字 → 纯白
    ("TIMColor", "Black"): WHITE,
    ("TIMColor", "DeepGray"): WHITE,
    ("TIMColor", "LightGray"): WHITE,
    ("TIMColor", "TextInWhite"): WHITE,
    ("TIMColor", "TextInBlue"): WHITE,
    ("TIMColor", "TextInButtonNormal"): WHITE,

    # ---- Color：通用控件表面 -------------------------------------------------
    ("Color", "Background"): "0x2a2a2a",
    ("Color", "OuterBorder"): "0x3c3c3c",
    ("Color", "CtrlBorderNormal"): "0x4a4a4a",
    ("Color", "CtrlBorderHoverGlow"): "0x3f6e8c",
    ("Color", "CtrlBorderPushedGlow"): "0x3f6e8c",
    ("Color", "CtrlBorderHover"): "0x5a8fc7",
    ("Color", "CtrlBorderPushed"): "0x5a8fc7",
    ("Color", "SelectedOuterBorder"): "0x2d7fd0",
    ("Color", "SelectedInnerBorder"): "0x3e6e96",
    ("Color", "SelectedBackground"): "0x2c4a66",
    ("Color", "SelectedOuterBorder2"): "0x8a6a3a",
    ("Color", "SelectedInnerBorder2"): "0x4a4038",
    ("Color", "SelectedBackground2"): "0x40352a",
    ("Color", "IconButtonInnerBorder"): "0x3c3c3c",
    ("Color", "IconButtonOuterBorder"): "0x4a4a4a",
    ("Color", "IconButtonGradualTop"): "0x3a3a3a",
    ("Color", "IconButtonGradualBottom"): "0x2e2e2e",
    ("Color", "ImageOuterBorder"): "0x4a4a4a",
    ("Color", "ImageInnerBorder"): "0x1a1a1a",
    ("Color", "ListItemBackground1"): "0x262626",
    ("Color", "ListItemBackground2"): "0x2e2e2e",
    ("Color", "ClientAreaGradualBottom"): "0x1f1f1f",
    ("Color", "MenuInnerBorder"): "0x3c3c3c",
    ("Color", "MenuOuterBorder"): "0x3c3c3c",
    ("Color", "MenuLeftBar"): "0x2a2a2a",
    ("Color", "EditDisableBackground"): "0x2a2a2a",

    # ---- TextColor / TextColor(TIM)：两个组，名字相同 ------------------------
    ("TextColor", "Text"): WHITE,
    ("TextColor", "UI"): WHITE,
    ("TextColor", "Disable"): WHITE,
    ("TextColor", "Reverse"): WHITE,
    ("TextColor", "Gray"): WHITE,
    ("TextColor", "Gray2"): WHITE,
    ("TextColor", "WBlogNick"): WHITE,
    ("TextColor", "WBlogWhiteHighlight"): WHITE,
    # 链接 / 警告保留能认出来的色相，但提亮
    ("TextColor", "LowLink"): "0x4d94ff",
    ("TextColor", "HighLink"): "0x4d94ff",
    ("TextColor", "HighLinkTips"): "0xff5a3c",
    ("TextColor", "HighLinkVip"): "0xffa07a",
    ("TextColor", "HighLinkHighlight"): "0x4d94ff",
    ("TextColor", "HighLinkHighlightVip"): "0xffa07a",
    ("TextColor", "HighLinkPushed"): "0x4d94ff",
    ("TextColor", "HighLinkPushedVip"): "0xffa07a",
    ("TextColor", "LightLink"): "0x4d94ff",
    ("TextColor", "NormalLink"): "0x4d94ff",
    ("TextColor", "NormalLinkHighlight"): "0x4d94ff",
    ("TextColor", "NormalLinkPushed"): "0x4d94ff",
    ("TextColor", "Menu"): "0xe5e8e8e8",
    ("TextColor", "WBlogLink"): "0x5aa9e6",
    ("TextColor", "WBlogInvite"): "0xff5a3c",
    ("TextColor", "NewHighLink"): "0x2bb7f5",
    ("TextColor", "NewHighLinkPushed"): "0x2bb7f5",
    ("TextColor", "NewHighLinkHighlight"): "0x2bb7f5",
    ("TextColor", "NewNormalLink"): "0x2bb7f5",
    ("TextColor", "NewNormalLinkHighlight"): "0x2bb7f5",
    ("TextColor", "NewNormalLinkPushed"): "0x0da3e5",

    # ---- BorderColor：边框 ---------------------------------------------------
    ("BorderColor", "Normal"): "0x3c3c3c",
    ("BorderColor", "Focus"): "0x4d8fd0",
    ("BorderColor", "Highlight"): "0x4d8fd0",
    ("BorderColor", "UI"): "0x3c3c3c",
    ("BorderColor", "Tab"): "0x3c3c3c",

    # ---- 富文本 --------------------------------------------------------------
    ("Rich_TextColor", "Normal"): WHITE,
    ("Rich_TextColor", "Gray"): WHITE,
    ("Rich_TextColor", "Title"): WHITE,
    ("Rich_TextColor", "Summary"): WHITE,
    ("Rich_TextColor", "Orange"): "0xff9345",
    ("Rich_TextColor", "Yellow"): "0xff8a3c",
    ("Rich_TextColor", "Red"): "0xff5a5a",
    ("Rich_TextColor", "Price"): "0xff5a5a",
    ("Rich_TextColor", "BuddyName"): "0xff9345",
    ("Rich_LinkColor", "Normal"): WHITE,
    ("Rich_LinkColor", "Heightlight"): "0x4d94ff",
    ("Rich_LinkColor", "Pushed"): "0x4d94ff",

    # ---- 杂项 ----------------------------------------------------------------
    ("GBKPopTip_color", "Title"): WHITE,
    ("GBKPopTip_color", "Text"): WHITE,
    ("GBKPopTip_color", "BigText"): WHITE,

    # ---- 朋友圈 (friend circle) -------------------------------------------
    ("FCColor", "MainContent"): "0x1f1f1f",
    ("FCColor", "SplitLineDeepGray"): "0x1affffff",
    ("FCColor", "TextDeepGray"): WHITE,
    ("FCColor", "TextMidGray"): WHITE,
    ("FCColor", "TextLightGray"): WHITE,
    ("FCColor", "TextWhite"): WHITE,
    ("FCColor", "TextBlack"): WHITE,
    ("FCColor", "HoverItem"): "0x2f2f2f",
    ("FCColor", "SelItem"): "0x3a3a3a",
    ("FCColor", "TextRed"): "0xff5a5a",
    ("FCColor", "TextLightBlue"): "0x4d94ff",
    ("FCColor", "TextLightBlueHover"): "0x4d94ff",
    ("FCColor", "TextLightBluePushed"): "0x4d94ff",
}

# 绝对不能碰的颜色
PROTECT = {("Color", "MaskColor")}

TG_RE = re.compile(r"<TG([^>]*)>")
TV_RE = re.compile(r"<TV([^>]*?)/>")


def parse_group(attrs):
    m = re.search(r'name="([^"]*)"', attrs)
    return m.group(1) if m else ""


def invert_lightness(hexval):
    """hexval like '0xRRGGBB' or '0xAARRGGBB' -> inverted-lightness colour."""
    s = hexval[2:]
    if len(s) == 6:
        alpha, rgb = None, s
    elif len(s) == 8:
        alpha, rgb = s[:2], s[2:]
    else:
        return hexval
    r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn > 18:            # saturated -> keep (brand colour)
        return hexval
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    nl = 1.0 - lum
    if mx == mn or r == g == b:
        nr = ng = nb = int(round(nl * 255))
    else:
        avg = (r + g + b) / 3.0
        nr, ng, nb = (int(max(0, min(255, round(nl * 255 + (c - avg))))) for c in (r, g, b))
    out = "%02x%02x%02x" % (nr, ng, nb)
    return "0x" + (alpha + out if alpha else out)


def main():
    path = sys.argv[1]
    revert = "--revert" in sys.argv
    if revert:
        shutil.copyfile(path + ".orig", path)
        print("reverted", path)
        return
    shutil.copyfile(path, path + ".orig")
    with io.open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()

    stats = {"explicit": 0, "auto": 0, "kept": 0}
    group = [""]

    def sub_group(m):
        group[0] = parse_group(m.group(1))
        return m.group(0)

    def sub_tv(m):
        attrs = m.group(1)
        if 'type="color"' not in attrs or 'value="' not in attrs:
            return m.group(0)
        name = re.search(r'name="([^"]*)"', attrs)
        val = re.search(r'value="([^"]*)"', attrs)
        if not name or not val:
            return m.group(0)
        name, old = name.group(1), val.group(1)
        if (group[0], name) in PROTECT:
            stats["kept"] += 1
            return m.group(0)
        new = EXPLICIT.get((group[0], name))
        if new is not None:
            stats["explicit"] += 1
        else:
            new = invert_lightness(old)
            if new == old:
                stats["kept"] += 1
                return m.group(0)
            stats["auto"] += 1
        return m.group(0).replace('value="%s"' % old, 'value="%s"' % new)

    out = []
    for line in text.splitlines(True):
        line = TG_RE.sub(sub_group, line)
        line = TV_RE.sub(sub_tv, line)
        out.append(line)
    text = "".join(out)
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)
    print("patched %s : explicit=%d auto=%d kept=%d"
          % (path, stats["explicit"], stats["auto"], stats["kept"]))


if __name__ == "__main__":
    main()
