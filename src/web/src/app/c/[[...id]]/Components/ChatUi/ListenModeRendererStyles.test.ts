import { readFileSync } from 'fs';
import path from 'path';

const readStylesheet = () =>
  readFileSync(path.join(__dirname, 'ListenModeRenderer.scss'), 'utf8');

const readChatUiStylesheet = () =>
  readFileSync(path.join(__dirname, 'ChatUi.module.scss'), 'utf8');

const normalizeStylesheet = (stylesheet: string) =>
  stylesheet.replace(/\s+/g, ' ');

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
    const normalizedStylesheet = normalizeStylesheet(stylesheet);
    const desktopWrapperSelector =
      '.listen-reveal-wrapper:not(.mobile):not(.listen-reveal-wrapper--classroom)';
    const browserFullscreenExcludedSelector =
      '.listen-slide-root:not(.slide--browser-fullscreen)';

    expect(chatUiStylesheet).toContain('--listen-player-footer-gap: 0px');
    expect(normalizedStylesheet).toContain(
      `${desktopWrapperSelector} ${browserFullscreenExcludedSelector} .listen-slide-player { bottom: var(--listen-slide-player-bottom-offset);`,
    );
    expect(normalizedStylesheet).toContain(
      [
        `${desktopWrapperSelector} .listen-slide-shell > .slide-ask-overlay`,
        `${desktopWrapperSelector} ${browserFullscreenExcludedSelector} .slide-ask-overlay`,
        `${desktopWrapperSelector} ${browserFullscreenExcludedSelector} .slide-interaction-overlay`,
      ].join(', ') +
        ' { --slide-player-bottom-offset: var(--listen-slide-player-bottom-offset);',
    );
    expect(normalizedStylesheet).toContain(
      `${desktopWrapperSelector} ${browserFullscreenExcludedSelector} .slide-subtitle-overlay { --slide-player-bottom-offset: var(--listen-slide-player-bottom-offset);`,
    );
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
