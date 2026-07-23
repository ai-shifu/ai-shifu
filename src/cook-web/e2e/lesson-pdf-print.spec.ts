import { expect, Page, test } from '@playwright/test';

type PrintLayoutMetrics = {
  pageWidth: number;
  sections: Array<{
    maxWidth: string;
    width: number;
  }>;
  snapshotMaxWidth: string;
  snapshotWidth: number;
  snapshotHeight: number;
  sourceWidth: number;
  sourceHeight: number;
  stageWidth: number;
  stageHeight: number;
  stageZoom: number;
  probeWidth: number;
  probeHeight: number;
  probeRightGap: number;
  probeBottomGap: number;
};

const readPrintLayoutMetrics = (page: Page) =>
  page.evaluate<PrintLayoutMetrics>(() => {
    const printPage = document.querySelector<HTMLElement>(
      '[data-lesson-print-scroll="true"] > [data-lesson-print-page="true"]',
    );
    const sections = Array.from(
      printPage?.querySelectorAll<HTMLElement>(
        ':scope > [data-print-section="true"]',
      ) ?? [],
    );
    const snapshot = printPage?.querySelector<HTMLElement>(
      '[data-lesson-print-iframe-snapshot="true"]',
    );
    const stage = snapshot?.shadowRoot?.querySelector<HTMLElement>(
      '[data-lesson-print-iframe-stage="true"]',
    );
    const probe = stage?.querySelector<HTMLElement>(
      '[data-print-scale-probe="true"]',
    );

    if (!printPage || !snapshot || !stage || !probe) {
      throw new Error('Lesson PDF print fixture is incomplete');
    }

    const snapshotRect = snapshot.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    const probeRect = probe.getBoundingClientRect();

    return {
      pageWidth: printPage.getBoundingClientRect().width,
      sections: sections.map(section => ({
        maxWidth: getComputedStyle(section).maxWidth,
        width: section.getBoundingClientRect().width,
      })),
      snapshotMaxWidth: getComputedStyle(snapshot).maxWidth,
      snapshotWidth: snapshotRect.width,
      snapshotHeight: snapshotRect.height,
      sourceWidth: Number.parseFloat(
        snapshot.style.getPropertyValue('--lesson-print-iframe-source-width'),
      ),
      sourceHeight: Number.parseFloat(
        snapshot.style.getPropertyValue('--lesson-print-iframe-source-height'),
      ),
      stageWidth: stageRect.width,
      stageHeight: stageRect.height,
      stageZoom: Number.parseFloat(getComputedStyle(stage).zoom),
      probeWidth: probeRect.width,
      probeHeight: probeRect.height,
      probeRightGap: stageRect.right - probeRect.right,
      probeBottomGap: stageRect.bottom - probeRect.bottom,
    };
  });

const expectPrintableWidthLayout = (metrics: PrintLayoutMetrics) => {
  expect(metrics.sections).toHaveLength(3);
  expect(metrics.snapshotMaxWidth).toBe('100%');
  for (const section of metrics.sections) {
    expect(section.maxWidth).toBe('none');
    expect(section.width).toBeCloseTo(metrics.pageWidth, 0);
  }

  const expectedSnapshotWidth = metrics.sections[1].width - 40;
  const expectedScale = expectedSnapshotWidth / metrics.sourceWidth;

  expect(metrics.snapshotWidth).toBeCloseTo(expectedSnapshotWidth, 0);
  expect(metrics.stageWidth).toBeCloseTo(metrics.snapshotWidth, 0);
  expect(metrics.stageHeight).toBeCloseTo(
    metrics.sourceHeight * expectedScale,
    0,
  );
  expect(metrics.snapshotHeight).toBeCloseTo(metrics.stageHeight, 0);
  expect(metrics.stageZoom).toBeCloseTo(expectedScale, 3);
  expect(metrics.probeWidth).toBeCloseTo(120 * expectedScale, 0);
  expect(metrics.probeHeight).toBeCloseTo(60 * expectedScale, 0);
  expect(metrics.probeRightGap).toBeCloseTo(0, 0);
  expect(metrics.probeBottomGap).toBeCloseTo(0, 0);
};

test('lesson PDF uses the printable width in every orientation', async ({
  page,
}) => {
  await page.goto('/login');
  await page.evaluate(() => {
    const fixture = document.createElement('main');
    fixture.dataset.lessonPrintPage = 'true';
    fixture.innerHTML = `
      <section data-lesson-print-scroll="true">
        <div data-lesson-print-page="true">
          <header data-print-section="true" style="box-sizing: border-box; margin: 0 auto; max-width: 1000px; padding: 0 20px;">
            Course header
          </header>
          <article data-print-section="true" style="box-sizing: border-box; margin: 0 auto; max-width: 1000px; padding: 0 20px;">
            Lesson content
            <div
              data-lesson-print-iframe-snapshot="true"
              style="--lesson-print-iframe-source-width: 960px; --lesson-print-iframe-source-height: 540px;"
            ></div>
          </article>
          <footer data-print-section="true" style="box-sizing: border-box; margin: 0 auto; max-width: 1000px; padding: 0 20px;">
            Course QR footer
          </footer>
        </div>
      </section>
    `;
    document.body.append(fixture);

    const snapshot = fixture.querySelector<HTMLElement>(
      '[data-lesson-print-iframe-snapshot="true"]',
    );
    if (!snapshot) {
      throw new Error('Lesson PDF snapshot fixture is missing');
    }

    const shadowRoot = snapshot.attachShadow({ mode: 'open' });
    const snapshotStyles = document.createElement('style');
    snapshotStyles.textContent = `
      :host {
        display: block;
        width: 100%;
        max-width: 100%;
        container-type: inline-size;
      }
      [data-lesson-print-iframe-stage='true'] {
        position: relative;
        width: var(--lesson-print-iframe-source-width);
        height: var(--lesson-print-iframe-source-height);
        overflow: hidden;
        zoom: calc(100cqw / var(--lesson-print-iframe-source-width));
      }
      [data-print-scale-probe='true'] {
        position: absolute;
        right: 0;
        bottom: 0;
        width: 120px;
        height: 60px;
      }
    `;
    const stage = document.createElement('div');
    stage.setAttribute('data-lesson-print-iframe-stage', 'true');
    const probe = document.createElement('div');
    probe.setAttribute('data-print-scale-probe', 'true');
    stage.appendChild(probe);
    shadowRoot.append(snapshotStyles, stage);
  });
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(() =>
    document.documentElement.classList.add('lesson-pdf-print'),
  );

  await page.setViewportSize({ width: 800, height: 1200 });
  await expect
    .poll(() =>
      page.evaluate(() => matchMedia('(orientation: portrait)').matches),
    )
    .toBe(true);
  const narrowPortrait = await readPrintLayoutMetrics(page);

  expect(narrowPortrait.pageWidth).toBeLessThan(1000);
  expect(narrowPortrait.stageZoom).toBeLessThan(1);
  expectPrintableWidthLayout(narrowPortrait);

  await page.setViewportSize({ width: 1200, height: 1600 });
  await expect
    .poll(() =>
      page.evaluate(() => matchMedia('(orientation: portrait)').matches),
    )
    .toBe(true);
  const portrait = await readPrintLayoutMetrics(page);

  expect(portrait.pageWidth).toBeGreaterThan(1000);
  expect(portrait.stageZoom).toBeGreaterThan(1);
  expectPrintableWidthLayout(portrait);

  await page.setViewportSize({ width: 1600, height: 1200 });
  await expect
    .poll(() =>
      page.evaluate(() => matchMedia('(orientation: landscape)').matches),
    )
    .toBe(true);
  const landscape = await readPrintLayoutMetrics(page);

  expect(landscape.pageWidth).toBeGreaterThan(1000);
  expect(landscape.stageZoom).toBeGreaterThan(portrait.stageZoom);
  expectPrintableWidthLayout(landscape);
});
