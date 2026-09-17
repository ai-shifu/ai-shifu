import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import ModelTierList from './ModelTierList';

const mockOptions = jest.fn();
jest.mock('@/api', () => ({
  __esModule: true,
  default: { getModelTierList: () => mockOptions() },
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key.split('.').at(-1) }),
}));

const options = ['fast', 'balanced', 'ultimate'].map((tier, index) => ({
  tier,
  available: index !== 2,
  credit_multiplier_label: `${index + 1}x`,
  model: 'hidden-physical-model',
}));

describe('ModelTierList', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = jest.fn();
  });
  beforeEach(() => {
    mockOptions.mockReset();
    mockOptions.mockResolvedValue(options);
  });

  it('shows exactly three tiers with rates and unavailable state, hiding model names', async () => {
    const onChange = jest.fn();
    render(
      <ModelTierList
        value={null}
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('combobox')).toHaveTextContent('legacy');
    await act(async () => {});
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' });
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(3));
    expect(screen.getByRole('option', { name: /ultimate/ })).toHaveAttribute(
      'data-disabled',
    );
    expect(screen.getByRole('option', { name: /balanced/ })).toHaveTextContent(
      '2x',
    );
    expect(screen.queryByText(/hidden-physical-model/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', { name: /balanced/ }));
    expect(onChange).toHaveBeenCalledWith('balanced');
    expect(mockOptions).toHaveBeenCalledTimes(2);
  });

  it('keeps a saved tier visible when the catalog fails and respects read-only', async () => {
    mockOptions.mockRejectedValue(new Error('offline'));
    render(
      <ModelTierList
        value='fast'
        onChange={jest.fn()}
        disabled
      />,
    );
    await act(async () => {});
    expect(screen.getByRole('combobox')).toHaveTextContent('fast');
    expect(screen.getByRole('combobox')).toBeDisabled();
  });
});
