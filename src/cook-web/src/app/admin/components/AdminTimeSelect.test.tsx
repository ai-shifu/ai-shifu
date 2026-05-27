import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import AdminTimeSelect, { parseAdminTimeValue } from './AdminTimeSelect';

const ControlledTimeSelect = ({
  initialValue,
  onChange,
  minTime,
  maxTime,
}: {
  initialValue: string;
  onChange: (value: string) => void;
  minTime?: string;
  maxTime?: string;
}) => {
  const [value, setValue] = useState(initialValue);
  return (
    <AdminTimeSelect
      value={value}
      minTime={minTime}
      maxTime={maxTime}
      onChange={nextValue => {
        setValue(nextValue);
        onChange(nextValue);
      }}
    />
  );
};

describe('AdminTimeSelect', () => {
  test('normalizes invalid time values to midnight', () => {
    expect(parseAdminTimeValue('08:30')).toEqual({
      hour: '08',
      minute: '30',
    });
    expect(parseAdminTimeValue('27:90')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('2023-10-27')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('2023-10-27Z')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('2023-10-27T00:00:00Z')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('08:30:15')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('08:30+08:00')).toEqual({
      hour: '00',
      minute: '00',
    });
    expect(parseAdminTimeValue('invalid-time')).toEqual({
      hour: '00',
      minute: '00',
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
    fireEvent.click(
      within(screen.getByRole('group', { name: 'Hour' })).getByRole('button', {
        name: '10',
      }),
    );
    expect(handleChange).toHaveBeenLastCalledWith('10:15');

    fireEvent.click(
      within(screen.getByRole('group', { name: 'Minute' })).getByRole(
        'button',
        { name: '45' },
      ),
    );

    expect(handleChange).toHaveBeenLastCalledWith('10:45');
  });

  test('disables options outside the min and max time range', () => {
    const handleChange = jest.fn();
    render(
      <ControlledTimeSelect
        initialValue='10:45'
        minTime='10:30'
        maxTime='11:15'
        onChange={handleChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '10:45' }));

    const hourGroup = screen.getByRole('group', { name: 'Hour' });
    const minuteGroup = screen.getByRole('group', { name: 'Minute' });

    expect(
      within(hourGroup).getByRole('button', { name: '09' }),
    ).toBeDisabled();
    expect(
      within(hourGroup).getByRole('button', { name: '12' }),
    ).toBeDisabled();
    expect(
      within(minuteGroup).getByRole('button', { name: '15' }),
    ).toBeDisabled();
    expect(
      within(minuteGroup).getByRole('button', { name: '30' }),
    ).not.toBeDisabled();

    fireEvent.click(within(hourGroup).getByRole('button', { name: '11' }));

    expect(handleChange).toHaveBeenLastCalledWith('11:00');
  });
});
