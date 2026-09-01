import { readFileSync } from 'fs';
import path from 'path';

const readStylesheet = () =>
  readFileSync(path.join(__dirname, 'ListenModeRenderer.scss'), 'utf8');

const readChatUiStylesheet = () =>
  readFileSync(path.join(__dirname, 'ChatUi.module.scss'), 'utf8');

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

  it('aligns desktop listen controls to the footer through one shared offset', () => {
    const stylesheet = readStylesheet();
    const chatUiStylesheet = readChatUiStylesheet();

    expect(chatUiStylesheet).toContain('--listen-player-footer-gap: 0px');
    expect(stylesheet).toMatch(
      /\.listen-slide-player\s*\{\s*bottom:\s*var\(--listen-slide-player-bottom-offset\)/,
    );
    expect(stylesheet).toMatch(
      /\.slide-ask-overlay,[\s\S]*?\.slide-interaction-overlay\s*\{\s*--slide-player-bottom-offset:\s*var\(--listen-slide-player-bottom-offset\)/,
    );
    expect(stylesheet).toMatch(
      /\.slide-subtitle-overlay\s*\{\s*--slide-player-bottom-offset:\s*var\(--listen-slide-player-bottom-offset\)/,
    );
    expect(stylesheet).toContain(
      ':not(.mobile):not(.listen-reveal-wrapper--classroom)',
    );
    expect(stylesheet).toContain(':not(.slide--browser-fullscreen)');
  });

  it('lets Slide size the mobile player grid from its rendered actions', () => {
    const stylesheet = readStylesheet();

    expect(stylesheet).not.toContain('--slide-player-mobile-control-count');
    expect(stylesheet).not.toContain(
      '.listen-slide-player-mobile .slide-player__controls',
    );
    expect(stylesheet).not.toContain('--slide-player-notes-arrow-offset');
    expect(stylesheet).not.toContain('.slide-player__interaction-arrow');
  });
});
