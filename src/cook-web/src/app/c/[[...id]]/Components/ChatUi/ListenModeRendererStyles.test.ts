import { readFileSync } from 'fs';
import path from 'path';

describe('ListenModeRenderer styles', () => {
  it('keeps mobile landscape interaction overlays compatible with slide drag offsets', () => {
    const stylesheet = readFileSync(
      path.join(__dirname, 'ListenModeRenderer.scss'),
      'utf8',
    );
    const ruleMatch = stylesheet.match(
      /\.listen-reveal-wrapper\.mobile\s+\.listen-slide-root--landscape\.slide--mobile-landscape\s+\.slide-interaction-overlay\s*\{([^}]+)\}/,
    );
    const ruleBody = ruleMatch?.[1];

    expect(ruleBody).toBeDefined();
    expect(ruleBody).toContain('var(--slide-interaction-drag-x, 0px)');
    expect(ruleBody).toContain('var(--slide-interaction-drag-y, 0px)');
    expect(ruleBody).not.toContain('transform: none');
  });
});
