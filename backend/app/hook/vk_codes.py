"""Windows Virtual-Key code -> human-readable name mapping.

Source: Microsoft docs (winuser.h). Covers the full Q6 HE surface:
modifiers, F1-F24, numpad, navigation, media keys, browser keys,
launcher keys, IME, and OEM keys (which are layout-dependent — for
the IT layout these still come through as VK_OEM_n / scancode pairs).
"""

from __future__ import annotations

VK_NAMES: dict[int, str] = {
    0x01: "VK_LBUTTON", 0x02: "VK_RBUTTON", 0x03: "VK_CANCEL",
    0x04: "VK_MBUTTON", 0x05: "VK_XBUTTON1", 0x06: "VK_XBUTTON2",
    0x08: "VK_BACK", 0x09: "VK_TAB", 0x0C: "VK_CLEAR", 0x0D: "VK_RETURN",
    0x10: "VK_SHIFT", 0x11: "VK_CONTROL", 0x12: "VK_MENU",
    0x13: "VK_PAUSE", 0x14: "VK_CAPITAL",
    0x15: "VK_KANA/HANGUL", 0x17: "VK_JUNJA", 0x18: "VK_FINAL",
    0x19: "VK_HANJA/KANJI", 0x1B: "VK_ESCAPE",
    0x1C: "VK_CONVERT", 0x1D: "VK_NONCONVERT", 0x1E: "VK_ACCEPT",
    0x1F: "VK_MODECHANGE",
    0x20: "VK_SPACE", 0x21: "VK_PRIOR", 0x22: "VK_NEXT",
    0x23: "VK_END", 0x24: "VK_HOME",
    0x25: "VK_LEFT", 0x26: "VK_UP", 0x27: "VK_RIGHT", 0x28: "VK_DOWN",
    0x29: "VK_SELECT", 0x2A: "VK_PRINT", 0x2B: "VK_EXECUTE",
    0x2C: "VK_SNAPSHOT", 0x2D: "VK_INSERT", 0x2E: "VK_DELETE", 0x2F: "VK_HELP",
    0x5B: "VK_LWIN", 0x5C: "VK_RWIN", 0x5D: "VK_APPS",
    0x5F: "VK_SLEEP",
    0x60: "VK_NUMPAD0", 0x61: "VK_NUMPAD1", 0x62: "VK_NUMPAD2",
    0x63: "VK_NUMPAD3", 0x64: "VK_NUMPAD4", 0x65: "VK_NUMPAD5",
    0x66: "VK_NUMPAD6", 0x67: "VK_NUMPAD7", 0x68: "VK_NUMPAD8",
    0x69: "VK_NUMPAD9",
    0x6A: "VK_MULTIPLY", 0x6B: "VK_ADD", 0x6C: "VK_SEPARATOR",
    0x6D: "VK_SUBTRACT", 0x6E: "VK_DECIMAL", 0x6F: "VK_DIVIDE",
    0x90: "VK_NUMLOCK", 0x91: "VK_SCROLL",
    0xA0: "VK_LSHIFT", 0xA1: "VK_RSHIFT",
    0xA2: "VK_LCONTROL", 0xA3: "VK_RCONTROL",
    0xA4: "VK_LMENU", 0xA5: "VK_RMENU",
    0xA6: "VK_BROWSER_BACK", 0xA7: "VK_BROWSER_FORWARD",
    0xA8: "VK_BROWSER_REFRESH", 0xA9: "VK_BROWSER_STOP",
    0xAA: "VK_BROWSER_SEARCH", 0xAB: "VK_BROWSER_FAVORITES",
    0xAC: "VK_BROWSER_HOME",
    0xAD: "VK_VOLUME_MUTE", 0xAE: "VK_VOLUME_DOWN", 0xAF: "VK_VOLUME_UP",
    0xB0: "VK_MEDIA_NEXT_TRACK", 0xB1: "VK_MEDIA_PREV_TRACK",
    0xB2: "VK_MEDIA_STOP", 0xB3: "VK_MEDIA_PLAY_PAUSE",
    0xB4: "VK_LAUNCH_MAIL", 0xB5: "VK_LAUNCH_MEDIA_SELECT",
    0xB6: "VK_LAUNCH_APP1", 0xB7: "VK_LAUNCH_APP2",
    0xBA: "VK_OEM_1", 0xBB: "VK_OEM_PLUS", 0xBC: "VK_OEM_COMMA",
    0xBD: "VK_OEM_MINUS", 0xBE: "VK_OEM_PERIOD",
    0xBF: "VK_OEM_2", 0xC0: "VK_OEM_3",
    0xDB: "VK_OEM_4", 0xDC: "VK_OEM_5", 0xDD: "VK_OEM_6",
    0xDE: "VK_OEM_7", 0xDF: "VK_OEM_8",
    0xE2: "VK_OEM_102",
    0xE5: "VK_PROCESSKEY", 0xE7: "VK_PACKET",
    0xF6: "VK_ATTN", 0xF7: "VK_CRSEL", 0xF8: "VK_EXSEL",
    0xF9: "VK_EREOF", 0xFA: "VK_PLAY", 0xFB: "VK_ZOOM",
    0xFD: "VK_PA1", 0xFE: "VK_OEM_CLEAR",
}

for _c in range(ord("0"), ord("9") + 1):
    VK_NAMES[_c] = f"VK_{chr(_c)}"
for _c in range(ord("A"), ord("Z") + 1):
    VK_NAMES[_c] = f"VK_{chr(_c)}"
for _i in range(1, 25):
    VK_NAMES[0x70 + _i - 1] = f"VK_F{_i}"


def name(vk: int) -> str:
    return VK_NAMES.get(vk, f"VK_0x{vk:02X}")


_PRETTY_OVERRIDES: dict[str, str] = {
    "VK_RETURN": "Enter",
    "VK_BACK": "Backspace",
    "VK_ESCAPE": "Esc",
    "VK_PRIOR": "Page Up",
    "VK_NEXT": "Page Down",
    "VK_CAPITAL": "Caps Lock",
    "VK_SNAPSHOT": "Print Screen",
    "VK_MENU": "Alt",
    "VK_LMENU": "Left Alt",
    "VK_RMENU": "Right Alt",
    "VK_CONTROL": "Ctrl",
    "VK_LCONTROL": "Left Ctrl",
    "VK_RCONTROL": "Right Ctrl",
    "VK_SHIFT": "Shift",
    "VK_LSHIFT": "Left Shift",
    "VK_RSHIFT": "Right Shift",
    "VK_LWIN": "Left Win",
    "VK_RWIN": "Right Win",
    "VK_APPS": "Menu",
    "VK_OEM_PLUS": "+",
    "VK_OEM_MINUS": "-",
    "VK_OEM_COMMA": ",",
    "VK_OEM_PERIOD": ".",
}


def pretty_name(vk: int) -> str:
    """Human-friendly label, e.g. 'Space', 'Enter', 'F5', 'A', 'Numpad 3'."""
    raw = VK_NAMES.get(vk)
    if raw is None:
        return f"0x{vk:02X}"
    if raw in _PRETTY_OVERRIDES:
        return _PRETTY_OVERRIDES[raw]
    s = raw[3:] if raw.startswith("VK_") else raw
    if s.startswith("NUMPAD"):
        return f"Numpad {s[6:]}"
    if s.startswith("F") and s[1:].isdigit():
        return s
    if len(s) == 1:
        return s
    return s.replace("_", " ").title()
