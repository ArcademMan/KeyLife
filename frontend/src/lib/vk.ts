// Win32 virtual-key helpers used across the keyboard views.

// Raw Input on Windows sometimes reports the *generic* VK_SHIFT/VK_CONTROL/
// VK_MENU (0x10/0x11/0x12) instead of the L/R-specific 0xA0..0xA5,
// distinguishing the two sides only via the E0 extended flag (bit 0x100 of
// the folded scancode) and the MakeCode. The layout JSON uses the L/R
// codes, so without this remap AltGr / Right Ctrl / Right Shift end up in
// a generic bucket that no layout key matches.
export function canonicalVk(vk: number, scancode: number): number {
  const ext = (scancode & 0x100) !== 0
  const make = scancode & 0xff
  if (vk === 0x10) return make === 0x36 ? 0xA1 : 0xA0
  if (vk === 0x11) return ext ? 0xA3 : 0xA2
  if (vk === 0x12) return ext ? 0xA5 : 0xA4
  return vk
}

// VK → backend name, used to recompute the `name` after vk canonicalization
// so display lookups land on the right pretty label.
export const VK_TO_NAME: Record<number, string> = {
  0xA0: 'VK_LSHIFT',   0xA1: 'VK_RSHIFT',
  0xA2: 'VK_LCONTROL', 0xA3: 'VK_RCONTROL',
  0xA4: 'VK_LMENU',    0xA5: 'VK_RMENU',
}

// Pretty labels for VK names that the layout collapses on purpose. The
// layout uses "Ctrl"/"Shift"/"Alt"/"Win" on the rectangles for visual
// fidelity, which makes the all-keys table ambiguous. The table overrides
// using the backend `name` (which carries the L/R info).
export const VK_NAME_PRETTY: Record<string, string> = {
  VK_LCONTROL: 'Left Ctrl',
  VK_RCONTROL: 'Right Ctrl',
  VK_LSHIFT:   'Left Shift',
  VK_RSHIFT:   'Right Shift',
  VK_LMENU:    'Left Alt',
  VK_RMENU:    'AltGr',
  VK_LWIN:     'Left Win',
  VK_RWIN:     'Right Win',
  VK_APPS:     'Menu',
}

export function displayName(
  vk: number,
  scancode: number,
  name: string,
  labelByExact?: Map<string, string>,
  labelByVk?: Map<number, string>,
): string {
  const pretty = VK_NAME_PRETTY[name]
  if (pretty) return pretty
  // Disambiguate Enter vs Numpad Enter via the E0 bit in the scancode.
  if (name === 'VK_RETURN') return (scancode & 0x100) ? 'Numpad Enter' : 'Enter'
  return labelByExact?.get(`${vk}:${scancode}`)
    ?? labelByVk?.get(vk)
    ?? name.replace(/^VK_/, '')
}

export type Category =
  | 'Letters' | 'Digits' | 'Punctuation' | 'Space'
  | 'Modifiers' | 'Navigation' | 'Editing' | 'Function' | 'Other'

export const MODIFIER_VKS: ReadonlySet<number> = new Set([
  0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C, 0x5D,
  0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
])

export function categorize(vk: number): Category {
  if (vk >= 0x41 && vk <= 0x5A) return 'Letters'
  if ((vk >= 0x30 && vk <= 0x39) || (vk >= 0x60 && vk <= 0x69)) return 'Digits'
  if (vk === 0x20) return 'Space'
  if (MODIFIER_VKS.has(vk)) return 'Modifiers'
  if (vk >= 0x70 && vk <= 0x87) return 'Function'
  if (vk === 0x08 || vk === 0x09 || vk === 0x0D || vk === 0x1B) return 'Editing'
  if ((vk >= 0x21 && vk <= 0x28) || vk === 0x2D || vk === 0x2E) return 'Navigation'
  // OEM punctuation: ; = , - . / ` [ \ ] '  + numpad operators
  if (
    (vk >= 0xBA && vk <= 0xC0) ||
    (vk >= 0xDB && vk <= 0xDF) ||
    (vk >= 0x6A && vk <= 0x6F)
  ) return 'Punctuation'
  return 'Other'
}

export const CATEGORY_ORDER: readonly Category[] = [
  'Letters', 'Digits', 'Punctuation', 'Space',
  'Modifiers', 'Navigation', 'Editing', 'Function', 'Other',
]

export const CATEGORY_COLORS: Record<Category, string> = {
  Letters:     '#7c5cff',
  Digits:      '#5b8cff',
  Punctuation: '#22d3ee',
  Space:       '#34d399',
  Modifiers:   '#f59e0b',
  Navigation:  '#fb7185',
  Editing:     '#a855f7',
  Function:    '#94a3b8',
  Other:       '#475569',
}

// Modifier groups for the modifier breakdown panel.
export const MODIFIER_GROUPS: ReadonlyArray<{ name: string; vks: readonly number[] }> = [
  { name: 'Shift', vks: [0x10, 0xA0, 0xA1] },
  { name: 'Ctrl',  vks: [0x11, 0xA2, 0xA3] },
  { name: 'Alt',   vks: [0x12, 0xA4, 0xA5] },
  { name: 'Win',   vks: [0x5B, 0x5C] },
  { name: 'Caps',  vks: [0x14] },
]
