export const getBoolEnv = (key) => {
  return process.env[key] === 'true';
};

export const getIntEnv = (key) => {
  return parseInt(process.env[key]);
};

export const getStringEnv = (key) => {
  return process.env[key];
};
