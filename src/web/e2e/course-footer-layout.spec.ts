import path from 'node:path';
import { expect, Page, test } from '@playwright/test';
import postcss from 'postcss';
import { compile } from 'sass';
import localByDefault from 'next/dist/compiled/postcss-modules-local-by-default';
import modulesScope from 'next/dist/compiled/postcss-modules-scope';

const courseDirectory = path.resolve('src/app/c/[[...id]]');
const chatDirectory = path.join(courseDirectory, 'Components/ChatUi');

// Use the production Sass and CSS Modules transforms so identically named
// classes from the two modules stay distinct, as they do in Next.js.
const moduleCss = async (file: string, prefix: string) =>
  (
    await postcss([
      localByDefault(),
      modulesScope({
        generateScopedName: (name: string) => `${prefix}_${name}`,
      }),
    ]).process(compile(file).css, { from: file })
  ).css;

let layoutCss: string;
test.beforeAll(async () => {
  layoutCss = (
    await Promise.all([
      moduleCss(path.join(chatDirectory, 'ChatComponents.module.scss'), 'chat'),
      moduleCss(path.join(chatDirectory, 'ChatUi.module.scss'), 'ui'),
      moduleCss(path.join(courseDirectory, 'page.module.scss'), 'page'),
    ])
  ).join('\n');
});

type Layout = {
  mobile?: boolean;
  preview?: boolean;
  notice?: boolean;
  mode?: 'read' | 'listen' | 'classroom';
  hiddenFooter?: boolean;
};

const renderCourse = async (page: Page, layout: Layout = {}) => {
  const { mobile, preview, notice, hiddenFooter, mode = 'read' } = layout;
  const slideMode = mode !== 'read';
  const pageClasses = [
    'page_newChatPage',
    slideMode ? 'page_listenMode' : '',
    preview ? 'page_previewMode' : '',
    notice ? 'page_lessonUpdateNoticeVisible' : '',
  ].join(' ');
  const uiClasses = [
    'ui_ChatUi',
    mobile ? 'ui_mobile' : '',
    slideMode ? 'ui_listenMode' : '',
    mode === 'classroom' ? 'ui_classroomMode' : '',
    preview && !mobile ? 'ui_previewModeDesktop' : '',
    hiddenFooter ? 'ui_hideMobileFooter' : '',
  ].join(' ');
  const contentClasses = `chat_chatComponents ui_chatComponents ${mobile ? 'chat_mobile' : ''}`;
  await page.setContent(`<!doctype html><html><head><style>
    *, *::before, *::after { box-sizing: border-box; }
    html, body { margin: 0; }
    :root { --app-viewport-block-unit: 1dvh; }
    ${layoutCss}
  </style></head><body>
    <main class="${pageClasses}" style="flex-direction: ${mobile ? 'column' : 'row'}; ${mobile ? '' : 'height: 100dvh;'}">
      ${mobile ? '<header class="page_chatMobileHeader">Course navigation</header>' : ''}
      <section class="${uiClasses}">
        ${mobile ? '' : `<header class="ui_header ${preview ? 'ui_previewHeader' : ''}">Course</header>`}
        <div data-content-shell class="${contentClasses}" style="position: relative; overflow: hidden; padding: 0;">
          ${
            slideMode
              ? '<div data-slide-content style="height: 100%; min-height: 0;">Slide content</div>'
              : `
            <div data-scroll class="${contentClasses}" style="width: 100%; height: 100%; overflow-y: auto;">
              <article>
                ${Array.from({ length: 100 }, (_, index) => `<p style="height: 48px; margin: 0;">Lesson paragraph ${index + 1}</p>`).join('')}
                <button type="button" onclick="this.dataset.clicked = 'true'">Continue lesson</button>
              </article>
            </div>
          `
          }
        </div>
        <footer class="ui_footer">AI-generated content | Powered by MarkdownFlow</footer>
      </section>
    </main>
  </body></html>`);
};

const readBounds = (page: Page) =>
  page.evaluate(() => {
    const rect = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector)!;
      const bounds = element.getBoundingClientRect();
      return { top: bounds.top, bottom: bounds.bottom, height: bounds.height };
    };
    return {
      shell: rect('[data-content-shell]'),
      content: rect('[data-scroll], [data-slide-content]'),
      footer: rect('.ui_footer'),
      viewportHeight: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      headerHeight:
        document
          .querySelector('.page_chatMobileHeader')
          ?.getBoundingClientRect().height ?? 0,
    };
  });

for (const viewport of [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet portrait', width: 834, height: 1194 },
  { name: 'mobile portrait', width: 390, height: 844, mobile: true },
  { name: 'mobile landscape', width: 844, height: 390, mobile: true },
]) {
  test(`reading stays above the footer on ${viewport.name}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await renderCourse(page, viewport);
    const scroll = page.locator('[data-scroll]');
    await scroll.evaluate(element => {
      element.scrollTop = 1200;
    });
    const bounds = await readBounds(page);
    expect(bounds.content.bottom).toBeLessThanOrEqual(bounds.footer.top + 1);
    expect(bounds.content.bottom).toBeCloseTo(bounds.shell.bottom, 0);
    expect(bounds.footer.bottom).toBeCloseTo(bounds.viewportHeight, 0);
    expect(bounds.documentHeight).toBeLessThanOrEqual(
      bounds.viewportHeight + 1,
    );
    await scroll.evaluate(element => {
      element.scrollTop = element.scrollHeight;
    });
    const button = page.getByRole('button', { name: 'Continue lesson' });
    const buttonBounds = (await button.boundingBox())!;
    expect(buttonBounds.y + buttonBounds.height).toBeLessThanOrEqual(
      bounds.footer.top + 1,
    );
    await button.click();
    await expect(button).toHaveAttribute('data-clicked', 'true');
  });
}

test('desktop preview preserves the preview header clearance', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await renderCourse(page, { preview: true });
  const bounds = await readBounds(page);
  expect(bounds.content.bottom).toBeCloseTo(bounds.footer.top, 0);
  expect(
    await page
      .locator('[data-scroll]')
      .evaluate(element => getComputedStyle(element).paddingTop),
  ).toBe('104px');
  expect(
    await page
      .locator('.ui_header')
      .evaluate(element => element.getBoundingClientRect().bottom),
  ).toBe(104);
});

for (const mode of ['listen', 'classroom'] as const) {
  test(`desktop ${mode} mode preserves its full slide canvas`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await renderCourse(page, { mode });
    const bounds = await readBounds(page);
    expect(bounds.shell.height).toBeCloseTo(bounds.viewportHeight, 0);
    expect(bounds.content.height).toBeCloseTo(bounds.shell.height, 0);
    expect(bounds.documentHeight).toBeLessThanOrEqual(
      bounds.viewportHeight + 1,
    );
  });
}

for (const layout of [
  { name: 'preview', preview: true },
  { name: 'update notice', notice: true },
  { name: 'preview and update notice', preview: true, notice: true },
]) {
  test(`mobile ${layout.name} leaves room for content and footer`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await renderCourse(page, { mobile: true, ...layout });
    const bounds = await readBounds(page);
    expect(bounds.shell.top).toBeCloseTo(bounds.headerHeight, 0);
    expect(bounds.content.bottom).toBeCloseTo(bounds.footer.top, 0);
    expect(bounds.footer.bottom).toBeCloseTo(bounds.viewportHeight, 0);
    expect(bounds.documentHeight).toBeLessThanOrEqual(
      bounds.viewportHeight + 1,
    );
  });
}

for (const mode of ['read', 'listen', 'classroom'] as const) {
  test(`hidden mobile footer reclaims its space in ${mode} mode`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await renderCourse(page, { mobile: true, mode });
    const visibleBounds = await readBounds(page);
    await renderCourse(page, { mobile: true, mode, hiddenFooter: true });
    await expect(page.locator('.ui_footer')).toBeHidden();
    const hiddenBounds = await readBounds(page);
    expect(
      hiddenBounds.content.height - visibleBounds.content.height,
    ).toBeCloseTo(visibleBounds.footer.height, 0);
    expect(hiddenBounds.content.bottom).toBeCloseTo(
      hiddenBounds.viewportHeight,
      0,
    );
    expect(hiddenBounds.documentHeight).toBeLessThanOrEqual(
      hiddenBounds.viewportHeight + 1,
    );
  });
}
