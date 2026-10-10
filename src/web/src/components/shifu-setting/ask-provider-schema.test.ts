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

  it('throws out_of_range error when number is outside schema bounds', () => {
    const schema = {
      properties: {
        top_k: { type: 'integer', minimum: 1, maximum: 10 },
      },
      required: [],
    };

    for (const badValue of ['12', '-3', '0', 11]) {
      expect(() =>
        buildAskProviderConfigForSubmit({
          schema,
          providerConfig: { top_k: badValue },
        }),
      ).toThrow(AskProviderSchemaValidationError);

      try {
        buildAskProviderConfigForSubmit({
          schema,
          providerConfig: { top_k: badValue },
        });
      } catch (error) {
        const typedError = error as AskProviderSchemaValidationError;
        expect(typedError.code).toBe('out_of_range');
        expect(typedError.field).toBe('top_k');
      }
    }
  });

  it('accepts numbers on schema bounds', () => {
    const schema = {
      properties: {
        top_k: { type: 'integer', minimum: 1, maximum: 10 },
      },
      required: [],
    };

    expect(
      buildAskProviderConfigForSubmit({
        schema,
        providerConfig: { top_k: '1' },
      }),
    ).toEqual({ top_k: 1 });
    expect(
      buildAskProviderConfigForSubmit({
        schema,
        providerConfig: { top_k: 10 },
      }),
    ).toEqual({ top_k: 10 });
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

  it('preserves advanced workflow bindings when the server allows additional properties', () => {
    const providerConfig = {
      api_key: 'saved-secret',
      workflow_id: 'workflow',
      context_key: 'classroom_context',
      query_key: 'input',
      parameters: { tenant: 'static' },
      extra_body: { bot_id: 'bot' },
      optional_text: '  ',
    };
    const original = JSON.parse(JSON.stringify(providerConfig));
    const result = buildAskProviderConfigForSubmit({
      schema: {
        additionalProperties: true,
        properties: {
          api_key: { type: 'string' },
          workflow_id: { type: 'string' },
          optional_text: { type: 'string' },
        },
        required: ['api_key', 'workflow_id'],
      },
      providerConfig,
    });
    expect(result).toEqual({
      api_key: 'saved-secret',
      workflow_id: 'workflow',
      context_key: 'classroom_context',
      query_key: 'input',
      parameters: { tenant: 'static' },
      extra_body: { bot_id: 'bot' },
    });
    expect(providerConfig).toEqual(original);
  });

  it.each([false, undefined])(
    'keeps undeclared fields excluded for additionalProperties=%s',
    additionalProperties => {
      expect(
        buildAskProviderConfigForSubmit({
          schema: {
            additionalProperties,
            properties: { api_key: { type: 'string' } },
          },
          providerConfig: { api_key: 'secret', context_key: 'context' },
        }),
      ).toEqual({ api_key: 'secret' });
    },
  );
});
