import React from 'react';

import { createRoot } from 'react-dom/client';

export function mountComponent(Comp: React.ReactElement, root = document.body) {
  const div = document.createElement('div');
  root.appendChild(div);
  const rootContainer = createRoot(div);

  const Clone = React.cloneElement(Comp, {
    // @ts-expect-error EXPECT
    onUnmount() {
      rootContainer.unmount()
      root.removeChild(div);
    },
  });

  rootContainer.render(Clone);

  return div;
}
