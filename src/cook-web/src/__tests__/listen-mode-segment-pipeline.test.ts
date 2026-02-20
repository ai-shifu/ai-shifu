jest.mock('markdown-flow-ui/renderer', () => ({
  splitContentSegments: jest.fn((raw: string) => {
    if ((raw || '').trimStart().startsWith('<table')) {
      return [{ type: 'sandbox', value: raw }];
    }
    return [{ type: 'text', value: raw }];
  }),
}));

import { splitListenModeSegments } from '@/c-utils/listen-mode/segment-pipeline';

describe('splitListenModeSegments sandbox table boundary', () => {
  it('keeps trailing non-table text outside sandbox table segment', () => {
    const raw = `<table><tr><td>A</td></tr></table>\n\nAfter table text`;
    const segments = splitListenModeSegments(raw);

    expect(segments).toHaveLength(2);
    expect(segments[0].type).toBe('sandbox');
    expect(String(segments[0].value)).toContain('<div><table>');
    expect(String(segments[0].value)).not.toContain('After table text');
    expect(segments[1].type).toBe('text');
    expect(String(segments[1].value)).toContain('After table text');
  });

  it('wraps pure html table sandbox blocks for blackboard rendering', () => {
    const raw = `<table><tr><td>A</td></tr></table>`;
    const segments = splitListenModeSegments(raw);

    expect(segments).toHaveLength(1);
    expect(segments[0].type).toBe('sandbox');
    expect(String(segments[0].value)).toContain('<div><table>');
  });
});
