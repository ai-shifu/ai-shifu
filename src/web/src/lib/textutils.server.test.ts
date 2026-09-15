describe('textutils server compatibility', () => {
  test('can be imported without navigator', async () => {
    const navigatorDescriptor = Object.getOwnPropertyDescriptor(
      globalThis,
      'navigator',
    );
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: undefined,
    });
    jest.resetModules();

    try {
      await expect(import('./textutils')).resolves.toEqual(
        expect.objectContaining({ copyText: expect.any(Function) }),
      );
    } finally {
      if (navigatorDescriptor) {
        Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
      }
    }
  });
});
