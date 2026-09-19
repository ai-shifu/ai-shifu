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
const options = [
  {
    index: '7',
    display_name: 'Research',
    available: false,
    credit_multiplier_label: '3x',
  },
  {
    index: '1',
    display_name: 'Everyday',
    available: true,
    credit_multiplier_label: '1x',
  },
  {
    index: '3',
    display_name: 'Deep thinking',
    available: true,
    credit_multiplier_label: '2x',
  },
].map(option => ({ ...option, model: 'hidden-physical-model' }));

describe('ModelTierList numbered choices', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = jest.fn();
  });
  beforeEach(() => {
    mockOptions.mockReset();
    mockOptions.mockResolvedValue(options);
  });
  it('sorts sparse configured indexes, uses configured names and hides physical IDs', async () => {
    const onChange = jest.fn();
    render(
      <ModelTierList
        value='1'
        onChange={onChange}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole('combobox')).toHaveTextContent('Everyday'),
    );
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' });
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(3));
    expect(
      screen
        .getAllByRole('option')
        .map(option => option.getAttribute('data-value') || option.textContent),
    ).toEqual(['Everyday1x', 'Deep thinking2x', 'Research3xunavailable']);
    expect(screen.getByRole('option', { name: /Research/ })).toHaveAttribute(
      'data-disabled',
    );
    expect(screen.queryByText(/hidden-physical-model/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', { name: /Deep thinking/ }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('3');
    expect(mockOptions).toHaveBeenCalledTimes(2);
  });
  it.each(['click', 'keyboard'])(
    'reports explicit %s selection of the effective default once',
    async method => {
      const onChange = jest.fn();
      render(
        <ModelTierList
          value='1'
          onChange={onChange}
          fallback
        />,
      );
      await waitFor(() =>
        expect(screen.getByRole('combobox')).toHaveTextContent('Everyday'),
      );
      expect(screen.getByRole('status')).toHaveTextContent('fallback');
      fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' });
      const option = await screen.findByRole('option', { name: /Everyday/ });
      if (method === 'keyboard') fireEvent.keyDown(option, { key: 'Enter' });
      else {
        fireEvent.pointerUp(option);
        fireEvent.click(option);
      }
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith('1');
    },
  );
  it('keeps the saved display label when the catalog fails and respects read-only', async () => {
    mockOptions.mockRejectedValue(new Error('offline'));
    render(
      <ModelTierList
        value='1'
        displayName='Everyday'
        onChange={jest.fn()}
        disabled
      />,
    );
    await act(async () => {});
    expect(screen.getByRole('combobox')).toHaveTextContent('Everyday');
    expect(screen.getByRole('combobox')).toBeDisabled();
  });
});
