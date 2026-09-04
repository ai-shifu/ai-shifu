import { readFileSync } from 'fs';
import path from 'path';

interface PublishedSourceMap {
  sourcesContent?: Array<string | null>;
}

const slidePackageRoot = path.dirname(
  path.dirname(require.resolve('markdown-flow-ui/slide')),
);

const readPublishedSource = (filename: 'Player' | 'Slide') => {
  const sourceMap = JSON.parse(
    readFileSync(
      path.join(
        slidePackageRoot,
        'dist',
        'components',
        'Slide',
        `${filename}.es.js.map`,
      ),
      'utf8',
    ),
  ) as PublishedSourceMap;
  const source = sourceMap.sourcesContent?.[0];

  expect(source).toBeTruthy();
  return source ?? '';
};

describe('markdown-flow-ui Slide package contract', () => {
  it('pins the published build that removes the Notes action and shortcut', () => {
    const packageJson = JSON.parse(
      readFileSync(path.join(slidePackageRoot, 'package.json'), 'utf8'),
    ) as { version?: string };
    const playerSource = readPublishedSource('Player');

    expect(packageJson.version).toBe('0.2.24');
    expect(playerSource).toContain('customActionList.length + 6');
    expect(playerSource).not.toContain('FilePenLine');
    expect(playerSource).not.toContain('notesLabel');
    expect(playerSource).not.toContain('slide-player__action--notes');
  });

  it('uses the published custom-action interaction exclusion', () => {
    const slideSource = readPublishedSource('Slide');

    expect(slideSource).toContain(
      'const closeInteractionOverlayForCustomAction = useCallback',
    );
    expect(slideSource).toContain('setIsInteractionOverlayOpen(false)');
    expect(slideSource).toContain('closeInteractionOverlayForCustomAction();');
    expect(slideSource).toContain('setActive: setPlayerCustomActionActive');
    expect(slideSource).toContain(
      'toggleActive: togglePlayerCustomActionActive',
    );
  });
});
