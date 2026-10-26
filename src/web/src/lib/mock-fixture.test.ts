import { loadStaticTextFixture } from './mock-fixture';

describe('loadStaticTextFixture', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('loads text from the requested fixture URL', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      text: jest.fn().mockResolvedValue('fixture-data'),
    });

    await expect(
      loadStaticTextFixture('/mock-fixtures/data.json'),
    ).resolves.toBe('fixture-data');

    expect(global.fetch).toHaveBeenCalledWith('/mock-fixtures/data.json');
  });
});
