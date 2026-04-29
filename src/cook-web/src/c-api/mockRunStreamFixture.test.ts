import {
  getMockRunFixtureMode,
  shouldUseMockStuckRunFixture,
} from './mockRunStreamFixture';

const setPageSearch = (search: string) => {
  window.history.pushState({}, '', `/${search}`);
};

describe('mock run stream fixture mode', () => {
  afterEach(() => {
    setPageSearch('');
  });

  it('enables the full test fixture for normal run requests', () => {
    setPageSearch('?mock_run_sse_fixture=test');

    expect(getMockRunFixtureMode({ input_type: 'normal' })).toBe('test');
  });

  it('keeps the stuck fixture mode for the existing debug flag', () => {
    setPageSearch('?mock_run_sse_fixture=stuck');

    expect(getMockRunFixtureMode({ input_type: 'normal' })).toBe('stuck');
    expect(shouldUseMockStuckRunFixture({ input_type: 'normal' })).toBe(true);
  });

  it('ignores fixture flags for non-normal requests', () => {
    setPageSearch('?mock_run_sse_fixture=test');

    expect(getMockRunFixtureMode({ input_type: 'ask' })).toBeNull();
  });
});
