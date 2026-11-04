import {
  parseRunEventObject,
  readDoneIsTerminal,
  readRunEventError,
} from './run-events';

describe('lesson stream run events', () => {
  it('reads an error message from each shape either stream sends', () => {
    expect(readRunEventError({ content: 'Plain' }).message).toBe('Plain');
    expect(readRunEventError({ data: 'From data' }).message).toBe('From data');
    expect(readRunEventError({ content: { content: 'Nested' } }).message).toBe(
      'Nested',
    );
    expect(readRunEventError({ content: { message: 'Field' } }).message).toBe(
      'Field',
    );
    expect(
      readRunEventError({ data: JSON.stringify({ mdflow: 'Script' }) }).message,
    ).toBe('Script');
    expect(readRunEventError({ message: 'Top level' }).message).toBe(
      'Top level',
    );
    expect(readRunEventError({}).message).toBe('');
  });

  it('reads the business code from the event before its payload', () => {
    expect(readRunEventError({ code: 7, content: { code: 8 } }).code).toBe(7);
    expect(readRunEventError({ content: { code: 8 } }).code).toBe(8);
    expect(
      readRunEventError({ data: JSON.stringify({ code: 9, message: 'x' }) })
        .code,
    ).toBe(9);
    expect(readRunEventError({ content: 'Plain' }).code).toBeUndefined();
  });

  it('searches content and data separately for the business code', () => {
    // A content object without a code must not hide the code in data.
    expect(readRunEventError({ content: {}, data: { code: 8 } }).code).toBe(8);
    expect(
      readRunEventError({
        content: { message: 'Unable to continue' },
        data: { code: 7101 },
      }),
    ).toEqual({ message: 'Unable to continue', code: 7101 });
  });

  it('keeps an unrecognized JSON error text instead of dropping it', () => {
    const raw = '{"error":"Service quota reached"}';
    expect(readRunEventError({ content: raw }).message).toBe(raw);
    expect(readRunEventError({ data: raw }).message).toBe(raw);
  });

  it('tells a terminal done from a block end and from silence', () => {
    expect(readDoneIsTerminal({ is_terminal: true })).toBe(true);
    expect(readDoneIsTerminal({ is_terminal: false })).toBe(false);
    expect(readDoneIsTerminal({ is_terminal: 'true' })).toBe(true);
    expect(readDoneIsTerminal({ is_terminal: 0 })).toBe(false);
    expect(readDoneIsTerminal({ content: { is_terminal: true } })).toBe(true);
    expect(
      readDoneIsTerminal({ data: JSON.stringify({ is_terminal: false }) }),
    ).toBe(false);
    expect(
      readDoneIsTerminal({
        is_terminal: false,
        content: { is_terminal: true },
      }),
    ).toBe(false);
    expect(readDoneIsTerminal({})).toBeNull();
  });

  it('searches content and data separately for the terminal flag', () => {
    // A content object without the flag must not hide the flag in data.
    expect(
      readDoneIsTerminal({
        content: { message: 'x' },
        data: { is_terminal: true },
      }),
    ).toBe(true);
    expect(
      readDoneIsTerminal({
        content: {},
        data: JSON.stringify({ is_terminal: false }),
      }),
    ).toBe(false);
    expect(readDoneIsTerminal({ content: {}, data: {} })).toBeNull();
  });

  it('parses only object payloads', () => {
    expect(parseRunEventObject('{"a":1}')).toEqual({ a: 1 });
    expect(parseRunEventObject('not json')).toBeNull();
    expect(parseRunEventObject('{broken')).toBeNull();
    expect(parseRunEventObject(3)).toBeNull();
  });
});
