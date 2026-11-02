/**
 * Defensive guard for React's DOM reconciler against external DOM mutation.
 *
 * Browser in-page translation (Edge/Chrome Translate) and some extensions
 * (e.g. Grammarly) rewrite text nodes that React owns — typically by wrapping
 * them in a <font> element. When React later runs its commit phase, the node
 * it remembers is no longer a child of the expected parent, so
 * `Node.prototype.removeChild` / `insertBefore` throw:
 *
 *   NotFoundError: Failed to execute 'insertBefore' on 'Node':
 *   The node before which the new node is to be inserted is not a child of this node.
 *
 * This error surfaces inside the reconciler's commit phase, which Next.js error
 * boundaries cannot catch, so it white-screens the whole page (reproducible on
 * Windows Edge in the lesson preview streaming view).
 *
 * The patch makes only the precise "node is not a child of this parent" case a
 * graceful no-op instead of throwing, letting the commit phase finish. Every
 * other condition still delegates to the native method and throws as before, so
 * genuine DOM misuse is not masked.
 *
 * `translate='no'` + the notranslate meta (see app/layout.tsx, app/metadata.tsx)
 * prevent the default trigger; this guard is the safety net for manual
 * translation and DOM-mutating extensions.
 */

const GUARD_FLAG = '__aiShifuDomGuardInstalled' as const;

type GuardedWindow = Window & { [GUARD_FLAG]?: boolean };

const warnOnce = (() => {
  let warned = false;
  return (method: string) => {
    if (warned) return;
    warned = true;
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn(
        `[DomReconcilerGuard] Suppressed a stale-node ${method} call, ` +
          'likely caused by browser translation or a DOM-mutating extension.',
      );
    }
  };
})();

export const installReactDomNodeGuard = (): void => {
  if (typeof window === 'undefined') return;

  const guardedWindow = window as GuardedWindow;
  if (guardedWindow[GUARD_FLAG]) return;
  guardedWindow[GUARD_FLAG] = true;

  const originalRemoveChild = Node.prototype.removeChild;
  const originalInsertBefore = Node.prototype.insertBefore;

  Node.prototype.removeChild = function removeChild<T extends Node>(
    this: Node,
    child: T,
  ): T {
    if (child instanceof Node && child.parentNode !== this) {
      // The node was detached out from under React (e.g. translated). Native
      // contract returns the removed node, so we honor that without throwing.
      // The `instanceof Node` guard keeps native TypeErrors for invalid args.
      warnOnce('removeChild');
      return child;
    }
    return originalRemoveChild.call(this, child) as T;
  } as typeof Node.prototype.removeChild;

  Node.prototype.insertBefore = function insertBefore<T extends Node>(
    this: Node,
    newNode: T,
    referenceNode: Node | null,
  ): T {
    if (referenceNode instanceof Node && referenceNode.parentNode !== this) {
      // The anchor was destroyed by an external mutation. Appending matches
      // React's effective intent for the lost reference. The `instanceof Node`
      // guard keeps native TypeErrors for invalid reference arguments.
      warnOnce('insertBefore');
      return this.appendChild(newNode) as unknown as T;
    }
    return originalInsertBefore.call(this, newNode, referenceNode) as T;
  } as typeof Node.prototype.insertBefore;
};
