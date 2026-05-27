import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AdminTimeSelect, { parseAdminTimeValue } from './AdminTimeSelect';

const ControlledTimeSelect = ({
  initialValue,
  onChange,
}: {
  initialValue: string;
  onChange: (value: string) => void;
}) => {
  const [value, setValue] = useState(initialValue);
  return (
    <AdminTimeSelect
      value={value}
      onChange={nextValue => {
        setValue(nextValue);
        onChange(nextValue);
      }}
    />
  );
};

describe('AdminTimeSelect', () => {
  test('normalizes invalid time values to midnight', () => {
    expect(parseAdminTimeValue('27:90')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('08:30')).toEqual({
      hour: '08',
      minute: '30',
    });
  });

  test('selects hour and minute with HH:mm output', () => {
    const handleChange = jest.fn();
    render(
      <ControlledTimeSelect
        initialValue='08:15'
        onChange={handleChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '08:15' }));
    fireEvent.click(screen.getAllByRole('button', { name: '10' })[0]);
    expect(handleChange).toHaveBeenLastCalledWith('10:15');

    fireEvent.click(screen.getByRole('button', { name: '45' }));

    expect(handleChange).toHaveBeenLastCalledWith('10:45');
  });
});
