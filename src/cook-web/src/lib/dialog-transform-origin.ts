'use client';

import * as React from 'react';

// How long a pointerdown stays valid as the "entry point" of a dialog.
// Keyboard-opened dialogs (or delayed opens) fall back to the default
// center-origin animation.
const RECENT_POINTER_MS = 1500;

let lastPointer: { x: number; y: number; time: number } | null = null;

if (typeof document !== 'undefined') {
  document.addEventListener(
    'pointerdown',
    event => {
      lastPointer = { x: event.clientX, y: event.clientY, time: Date.now() };
    },
    true,
  );
}

/**
 * Returns a ref callback that anchors a dialog's zoom animation to the
 * position of the pointer interaction that opened it, so the dialog appears
 * to grow out of (and collapse back into) its actual entry point instead of
 * the viewport's top-left corner.
 */
export function useTriggerTransformOrigin() {
  return React.useCallback((node: HTMLElement | null) => {
    if (!node) return;
    const pointer = lastPointer;
    if (!pointer || Date.now() - pointer.time > RECENT_POINTER_MS) return;
    const rect = node.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;
    node.style.transformOrigin = `${pointer.x - rect.left}px ${pointer.y - rect.top}px`;
  }, []);
}

export function composeRefs<T>(
  ...refs: Array<React.Ref<T> | undefined>
): React.RefCallback<T> {
  return node => {
    for (const ref of refs) {
      if (typeof ref === 'function') {
        ref(node);
      } else if (ref) {
        (ref as React.MutableRefObject<T | null>).current = node;
      }
    }
  };
}
