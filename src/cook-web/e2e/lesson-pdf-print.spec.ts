import { expect, Page, test } from '@playwright/test';

type PrintLayoutMetrics = {
  pageWidth: number;
  sections: Array<{
    maxWidth: string;
    width: number;
  }>;
  snapshotMaxWidth: string;
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

    if (!printPage || !snapshot) {
      throw new Error('Lesson PDF print fixture is incomplete');
    }

    return {
      pageWidth: printPage.getBoundingClientRect().width,
      sections: sections.map(section => ({
        maxWidth: getComputedStyle(section).maxWidth,
        width: section.getBoundingClientRect().width,
      })),
      snapshotMaxWidth: getComputedStyle(snapshot).maxWidth,
    };
  });

test('lesson PDF sections use the printable width only in landscape', async ({
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
            <div data-lesson-print-iframe-snapshot="true">Embedded lesson</div>
          </article>
          <footer data-print-section="true" style="box-sizing: border-box; margin: 0 auto; max-width: 1000px; padding: 0 20px;">
            Course QR footer
          </footer>
        </div>
      </section>
    `;
    document.body.append(fixture);
  });
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(() =>
    document.documentElement.classList.add('lesson-pdf-print'),
  );

  await page.setViewportSize({ width: 1200, height: 1600 });
  await expect
    .poll(() =>
      page.evaluate(() => matchMedia('(orientation: portrait)').matches),
    )
    .toBe(true);
  const portrait = await readPrintLayoutMetrics(page);

  expect(portrait.pageWidth).toBeGreaterThan(1000);
  expect(portrait.sections).toHaveLength(3);
  expect(portrait.snapshotMaxWidth).toBe('100%');
  for (const section of portrait.sections) {
    expect(section.maxWidth).toBe('1000px');
    expect(section.width).toBeCloseTo(1000, 0);
    expect(section.width).toBeLessThan(portrait.pageWidth);
  }

  await page.setViewportSize({ width: 1600, height: 1200 });
  await expect
    .poll(() =>
      page.evaluate(() => matchMedia('(orientation: landscape)').matches),
    )
    .toBe(true);
  const landscape = await readPrintLayoutMetrics(page);

  expect(landscape.pageWidth).toBeGreaterThan(1000);
  expect(landscape.sections).toHaveLength(3);
  expect(landscape.snapshotMaxWidth).toBe('100%');
  for (const section of landscape.sections) {
    expect(section.maxWidth).toBe('none');
    expect(section.width).toBeCloseTo(landscape.pageWidth, 0);
  }
});
