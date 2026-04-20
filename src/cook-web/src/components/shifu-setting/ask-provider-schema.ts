export type AskProviderSchemaField = {
  type?: string;
  format?: string;
  title?: string;
  description?: string;
};

export type AskProviderJsonSchema = {
  properties?: Record<string, AskProviderSchemaField>;
  required?: string[];
};

export type BuildAskProviderConfigParams = {
  schema?: AskProviderJsonSchema | null;
  providerConfig: Record<string, unknown>;
  objectInputs?: Record<string, string>;
};

export type AskProviderValidationCode = 'required' | 'invalid_json';

export class AskProviderSchemaValidationError extends Error {
  code: AskProviderValidationCode;
  field: string;

  constructor(code: AskProviderValidationCode, field: string) {
    super(`${code}:${field}`);
    this.name = 'AskProviderSchemaValidationError';
    this.code = code;
    this.field = field;
  }
}

const isMissing = (value: unknown): boolean => {
  if (value === undefined || value === null) {
    return true;
  }
  if (typeof value === 'string') {
    return value.trim() === '';
  }
  return false;
};

export const buildAskProviderConfigForSubmit = ({
  schema,
  providerConfig,
  objectInputs = {},
}: BuildAskProviderConfigParams): Record<string, unknown> => {
  const result: Record<string, unknown> = {};
  const properties = schema?.properties || {};
  const requiredFields = new Set(schema?.required || []);

  for (const [field, fieldSchema] of Object.entries(properties)) {
    const fieldType = String(fieldSchema?.type || 'string');
    const required = requiredFields.has(field);

    if (fieldType === 'object') {
      const rawValue =
        objectInputs[field] ??
        JSON.stringify(providerConfig[field] ?? {}, null, 2);
      const trimmed = String(rawValue || '').trim();
      if (!trimmed) {
        if (required) {
          throw new AskProviderSchemaValidationError('required', field);
        }
        continue;
      }
      try {
        const parsed = JSON.parse(trimmed);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('invalid object');
        }
        result[field] = parsed;
      } catch {
        throw new AskProviderSchemaValidationError('invalid_json', field);
      }
      continue;
    }

    if (fieldType === 'number' || fieldType === 'integer') {
      const rawNumber = providerConfig[field];
      if (isMissing(rawNumber)) {
        if (required) {
          throw new AskProviderSchemaValidationError('required', field);
        }
        continue;
      }
      const parsed = Number(rawNumber);
      if (Number.isNaN(parsed)) {
        throw new AskProviderSchemaValidationError('invalid_json', field);
      }
      result[field] = fieldType === 'integer' ? Math.round(parsed) : parsed;
      continue;
    }

    if (fieldType === 'boolean') {
      result[field] = Boolean(providerConfig[field]);
      continue;
    }

    const stringValue = String(providerConfig[field] ?? '').trim();
    if (!stringValue) {
      if (required) {
        throw new AskProviderSchemaValidationError('required', field);
      }
      continue;
    }
    result[field] = stringValue;
  }

  return result;
};
