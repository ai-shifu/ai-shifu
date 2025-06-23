export const SHORTCUT_IDS = {
  CONTINUE: 'continue',
  ASK: 'ask',
  SHORTCUT: 'shortcut',
}

export const shortcutKeys = [
  {
    id: SHORTCUT_IDS.CONTINUE,
    keys: ['space'],
    macKeys: ['space'],
  },
  {
    id: SHORTCUT_IDS.ASK,
    keys: ['ctrl', 'shift', 'a'],
    macKeys: ['cmd', 'shift', 'a'],
  },
  {
    id: SHORTCUT_IDS.SHORTCUT,
    keys: ['ctrl', '/'],
    macKeys: ['cmd', '/'],
  }
];

export const findShortcutKeyOption = (id) => {
  return shortcutKeys.find((item) => item.id === id);
}

export const genHotKeyIdentifier = (id, inMacOs) => {
  const option = findShortcutKeyOption(id);
  if (!option) {
    return '';
  }

  return inMacOs ? option.macKeys.join('+') : option.keys.join('+');
}
