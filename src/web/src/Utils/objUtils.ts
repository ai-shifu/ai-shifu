import { snakeToCamel, camelToSnake } from './textutils';

// Use Object.prototype.hasOwnProperty.call for safe property checks

// Convert object keys from snake_case to camelCase
export const convertKeysToCamelCase = (obj: unknown): unknown => {
    if (Array.isArray(obj)) {
        return obj.map(convertKeysToCamelCase);
    } else if (obj !== null && typeof obj === 'object') {
        const newObj: Record<string, unknown> = {};
        for (const key in obj) {
            if (Object.prototype.hasOwnProperty.call(obj, key)) {
                const newKey = snakeToCamel(key);
                newObj[newKey] = convertKeysToCamelCase((obj as Record<string, unknown>)[key]);
            }
        }
        return newObj;
    }
    return obj;
}

// Convert object keys from camelCase to snake_case
export const convertKeysToSnakeCase = (obj: unknown): unknown => {
  if (Array.isArray(obj)) {
      return obj.map(convertKeysToSnakeCase);
  } else if (obj !== null && typeof obj === 'object') {
      const newObj: Record<string, unknown> = {};
      for (const key in obj) {
          if (Object.prototype.hasOwnProperty.call(obj, key)) {
              const newKey = camelToSnake(key);
              newObj[newKey] = convertKeysToSnakeCase((obj as Record<string, unknown>)[key]);
          }
      }
      return newObj;
  }
  return obj;
}
