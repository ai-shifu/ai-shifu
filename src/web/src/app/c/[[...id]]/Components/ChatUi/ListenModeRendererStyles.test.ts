import { readFileSync } from 'fs';
import path from 'path';

const readStylesheet = () =>
  readFileSync(path.join(__dirname, 'ListenModeRenderer.scss'), 'utf8');

describe('ListenModeRenderer styles', () => {
  it('keeps mobile landscape interaction overlays compatible with slide drag offsets', () => {
    const stylesheet = readStylesheet();
    const ruleMatch = stylesheet.match(
      /\.listen-reveal-wrapper\.mobile\s+\.listen-slide-root--landscape\.slide--mobile-landscape\s+\.slide-interaction-overlay\s*\{([^}]+)\}/,
    );
    const ruleBody = ruleMatch?.[1];

    expect(ruleBody).toBeDefined();
    expect(ruleBody).toContain('var(--slide-interaction-drag-x, 0px)');
    expect(ruleBody).toContain('var(--slide-interaction-drag-y, 0px)');
    expect(ruleBody).not.toContain('transform: none');
  });

  it('keeps host-managed ask and mobile layouts on reserved player space', () => {
    const stylesheet = readStylesheet();
    const askRuleMatch = stylesheet.match(
      /\.slide-ask-overlay--with-player\s*\{([^}]+)\}/,
    );
    const askRuleBody = askRuleMatch?.[1];

    expect(askRuleBody).toBeDefined();
    expect(askRuleBody).toContain('var(--slide-player-height)');
    expect(stylesheet).toContain('&.listen-reveal-wrapper--with-player');
    expect(stylesheet).not.toContain('.slide-ask-overlay--standalone');
  });
});
