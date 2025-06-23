import { snakeToCamel, camelToSnake } from './textutils';

// Convert object keys from snake_case to camelCase
export const convertKeysToCamelCase = (obj) => {
    if (Array.isArray(obj)) {
        return obj.map(convertKeysToCamelCase);
    } else if (obj !== null && typeof obj === 'object') {
        const newObj = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                const newKey = snakeToCamel(key);
                newObj[newKey] = convertKeysToCamelCase(obj[key]);
            }
        }
        return newObj;
    }
    return obj;
}

// Convert object keys from camelCase to snake_case
export const convertKeysToSnakeCase = (obj) => {
  if (Array.isArray(obj)) {
      return obj.map(convertKeysToSnakeCase);
  } else if (obj !== null && typeof obj === 'object') {
      const newObj = {};
      for (const key in obj) {
          if (obj.hasOwnProperty(key)) {
              const newKey = camelToSnake(key);
              newObj[newKey] = convertKeysToSnakeCase(obj[key]);
          }
      }
      return newObj;
  }
  return obj;
}
