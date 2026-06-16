/** Design tokens — exact values from MailCull.dc.html */
export const C = {
  bg:         '#0E0F12',
  panel:      '#15171B',
  panel2:     '#1B1E23',
  border:     '#24272E',
  borderHov:  '#31353D',
  borderSub:  '#1F2228',
  borderDark: '#16181C',

  text:       '#E2E5EA',
  textMuted:  '#99A0AC',
  textFaint:  '#7B828E',
  textDim:    '#5A6068',
  textDimmer: '#4C525C',
  textGhost:  '#3C414B',
  textMono:   '#6E7682',

  teal:       '#2BB3A3',
  tealBright: '#3FD0BC',
  tealBg:     '#11302C',
  tealBorder: '#1E5C54',
  tealHov:    '#143A34',

  red:        '#E5484D',
  redBright:  '#F0696D',
  redBg:      '#2A1416',
  redBorder:  '#5A2528',
  redText:    '#B06B6E',

  amber:      '#E3B341',
  amberBg:    '#24210E',
  amberBorder:'#5A511E',
  amberDim:   '#9C8A4A',

  green:      '#3FB860',
  greenBg:    '#0F2417',
  greenBorder:'#235235',

  blue:       '#4C8DF0',
  blueBg:     '#0F1B33',

  cyan:       '#4FB0C6',
  cyanBg:     '#0E2429',
} as const;

export const CAT_COLORS: Record<string, [string, string]> = {
  Marketing:    [C.amber,  '#221E0C'],
  Newsletter:   [C.blue,   '#0F1B33'],
  Transactional:[C.green,  '#0F2417'],
  Social:       [C.cyan,   '#0E2429'],
  Spam:         [C.red,    '#27151B'],
  Personal:     [C.textMuted, '#1B1E23'],
};

export const CAP_COLORS: Record<string, [string, string]> = {
  one_click: [C.green,  '#0F2417'],
  link:      [C.amber,  '#221E0C'],
  mailto:    [C.blue,   '#0F1B33'],
  none:      [C.textFaint, '#1B1E23'],
};

export const CAP_LABELS: Record<string, string> = {
  one_click: 'One-click',
  link: 'Needs link',
  mailto: 'Mailto',
  none: 'Not possible',
};

export const DEC_LABELS: Record<string, string> = {
  keep: 'Keep',
  unsubscribe: 'Unsubscribe',
  mute: 'Mute',
  delete: 'Delete',
  archive: 'Archive',
  transactional: 'Transactional',
  snooze: 'Snooze',
};
