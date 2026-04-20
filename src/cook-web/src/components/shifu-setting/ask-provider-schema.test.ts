import {
  AskProviderSchemaValidationError,
  buildAskProviderConfigForSubmit,
} from '@/components/shifu-setting/ask-provider-schema';

describe('buildAskProviderConfigForSubmit', () => {
  const schema = {
    properties: {
      bot_id: { type: 'string' },
      timeout_seconds: { type: 'number' },
      max_tokens: { type: 'integer' },
      stream: { type: 'boolean' },
      extra_body: { type: 'object' },
    },
    required: ['bot_id', 'extra_body'],
  };

  it('builds typed config from schema', () => {
    const result = buildAskProviderConfigForSubmit({
      schema,
      providerConfig: {
        bot_id: 'bot-123',
        timeout_seconds: '8.5',
        max_tokens: '32.9',
        stream: 1,
      },
      objectInputs: {
        extra_body: '{"scene":"lesson"}',
      },
    });

    expect(result).toEqual({
      bot_id: 'bot-123',
      timeout_seconds: 8.5,
      max_tokens: 33,
      stream: true,
      extra_body: { scene: 'lesson' },
    });
  });

  it('throws required validation error when required field is missing', () => {
    expect(() =>
      buildAskProviderConfigForSubmit({
        schema,
        providerConfig: {
          bot_id: '',
        },
        objectInputs: {
          extra_body: '{"scene":"lesson"}',
        },
      }),
    ).toThrow(AskProviderSchemaValidationError);

    try {
      buildAskProviderConfigForSubmit({
        schema,
        providerConfig: {
          bot_id: '',
        },
        objectInputs: {
          extra_body: '{"scene":"lesson"}',
        },
      });
    } catch (error) {
      const typedError = error as AskProviderSchemaValidationError;
      expect(typedError.code).toBe('required');
      expect(typedError.field).toBe('bot_id');
    }
  });

  it('throws invalid_json error when object field is not valid json object', () => {
    expect(() =>
      buildAskProviderConfigForSubmit({
        schema,
        providerConfig: {
          bot_id: 'bot-123',
        },
        objectInputs: {
          extra_body: 'not-json',
        },
      }),
    ).toThrow(AskProviderSchemaValidationError);

    try {
      buildAskProviderConfigForSubmit({
        schema,
        providerConfig: {
          bot_id: 'bot-123',
        },
        objectInputs: {
          extra_body: 'not-json',
        },
      });
    } catch (error) {
      const typedError = error as AskProviderSchemaValidationError;
      expect(typedError.code).toBe('invalid_json');
      expect(typedError.field).toBe('extra_body');
    }
  });

  it('skips optional empty fields', () => {
    const result = buildAskProviderConfigForSubmit({
      schema: {
        properties: {
          optional_text: { type: 'string' },
          optional_number: { type: 'number' },
        },
        required: [],
      },
      providerConfig: {
        optional_text: ' ',
        optional_number: '',
      },
    });

    expect(result).toEqual({});
  });
});
