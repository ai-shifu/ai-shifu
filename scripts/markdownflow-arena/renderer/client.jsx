import React from 'react';
import { createRoot } from 'react-dom/client';
import { ContentRender } from 'markdown-flow-ui/renderer';
import { Slide } from 'markdown-flow-ui/slide';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
import 'markdown-flow-ui/dist/markdown-flow-ui-lib.css';
import './render.css';

const root = createRoot(document.getElementById('root'));

window.renderArena = (artifact, step = 0) => {
  const direction = artifact.locale === 'ar-SA' ? 'rtl' : 'ltr';
  document.documentElement.lang = artifact.locale;
  document.documentElement.dir = direction;
  document.documentElement.dataset.mode = artifact.mode;
  if (artifact.mode === 'slides') {
    let markerIndex = -1;
    const elements = artifact.elements.map((element) => {
      if (element.is_marker) markerIndex += 1;
      return {
        ...element,
        is_renderable: element.is_marker ? markerIndex === step : false,
      };
    });
    root.render(
      <div
        id="capture"
        className="arena-slide"
        lang={artifact.locale}
        dir={direction}
      >
        <Slide
          key={step}
          elementList={elements}
          locale={artifact.locale}
          lang={artifact.locale}
          dir={direction}
          playerEnabled={false}
          enableKeyboardShortcuts={false}
          disableLoadingOverlay
        />
      </div>,
    );
  } else {
    root.render(
      <div
        id="capture"
        className="arena-reading"
        lang={artifact.locale}
        dir={direction}
      >
        <ContentRender
          content={artifact.content}
          locale={artifact.locale}
          lang={artifact.locale}
          dir={direction}
          enableTypewriter={false}
          readonly
          disableSandboxLoadingOverlay
        />
      </div>,
    );
  }
};
