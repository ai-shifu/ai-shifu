import { installReactDomNodeGuard } from './domReconcilerGuard';

const GUARD_FLAG = '__aiShifuDomGuardInstalled';

describe('installReactDomNodeGuard', () => {
  const nativeRemoveChild = Node.prototype.removeChild;
  const nativeInsertBefore = Node.prototype.insertBefore;

  afterEach(() => {
    // Restore native prototype methods so the global patch never leaks into
    // other suites.
    Node.prototype.removeChild = nativeRemoveChild;
    Node.prototype.insertBefore = nativeInsertBefore;
    delete (window as unknown as Record<string, unknown>)[GUARD_FLAG];
  });

  /** Simulates Edge Translate wrapping a node's child in a <font> element. */
  const detachIntoFont = (parent: Node, child: Node) => {
    const font = document.createElement('font');
    nativeInsertBefore.call(parent, font, child);
    font.appendChild(child); // child.parentNode is now <font>, not parent
    return font;
  };

  it('reproduces the native NotFoundError before install (models the real bug)', () => {
    const parent = document.createElement('div');
    const child = document.createElement('span');
    parent.appendChild(child);
    detachIntoFont(parent, child);

    expect(() => parent.removeChild(child)).toThrow();
  });

  it('removeChild of a non-child node no longer throws and returns the node', () => {
    installReactDomNodeGuard();

    const parent = document.createElement('div');
    const child = document.createElement('span');
    parent.appendChild(child);
    detachIntoFont(parent, child);

    let result: Node | undefined;
    expect(() => {
      result = parent.removeChild(child);
    }).not.toThrow();
    expect(result).toBe(child);
  });

  it('insertBefore with a stale reference appends instead of throwing', () => {
    installReactDomNodeGuard();

    const parent = document.createElement('div');
    const anchor = document.createElement('span');
    parent.appendChild(anchor);
    detachIntoFont(parent, anchor); // anchor.parentNode is now <font>

    const newNode = document.createElement('em');
    expect(() => parent.insertBefore(newNode, anchor)).not.toThrow();
    expect(newNode.parentNode).toBe(parent);
    expect(parent.lastChild).toBe(newNode);
  });

  it('keeps the happy path identical to native', () => {
    installReactDomNodeGuard();

    const parent = document.createElement('div');
    const a = document.createElement('span');
    const b = document.createElement('span');
    parent.appendChild(b);

    // Legitimate insertBefore: insert a before existing child b.
    parent.insertBefore(a, b);
    expect(Array.from(parent.childNodes)).toEqual([a, b]);

    // Legitimate removeChild.
    const removed = parent.removeChild(a);
    expect(removed).toBe(a);
    expect(Array.from(parent.childNodes)).toEqual([b]);
  });

  it('is idempotent: installing twice does not re-wrap the prototype', () => {
    installReactDomNodeGuard();
    const afterFirst = Node.prototype.removeChild;
    installReactDomNodeGuard();
    expect(Node.prototype.removeChild).toBe(afterFirst);
  });

  it('does not mask unrelated errors (invalid newNode still throws)', () => {
    installReactDomNodeGuard();

    const parent = document.createElement('div');
    const anchor = document.createElement('span');
    parent.appendChild(anchor);

    // anchor is a real child, so the guard delegates to native insertBefore,
    // which must still reject a non-Node argument.
    expect(() =>
      parent.insertBefore('not-a-node' as unknown as Node, anchor),
    ).toThrow();
  });

  it('does not mask invalid (non-Node) referenceNode arguments', () => {
    installReactDomNodeGuard();

    const parent = document.createElement('div');
    const newNode = document.createElement('span');

    // A non-Node referenceNode must reach native insertBefore and throw,
    // not be treated as a stale-node fallback and silently appended.
    expect(() =>
      parent.insertBefore(newNode, 'not-a-node' as unknown as Node),
    ).toThrow();
    expect(parent.childNodes.length).toBe(0);
  });

  it('does not mask invalid (non-Node) removeChild arguments', () => {
    installReactDomNodeGuard();

    const parent = document.createElement('div');

    // A non-Node child must reach native removeChild and throw, not be
    // returned as a stale node.
    expect(() => parent.removeChild('not-a-node' as unknown as Node)).toThrow();
  });
});
