export interface RuntimeConfig {
  siteHost: string;
}

const defaultConfig: RuntimeConfig = {
  siteHost: 'http://localhost:8081',
};

let globalConfig: RuntimeConfig = { ...defaultConfig };

export function setRuntimeConfig(config: Partial<RuntimeConfig>) {
  globalConfig = { ...globalConfig, ...config };
}

export function getRuntimeConfig(): RuntimeConfig {
  return globalConfig;
}

export function getSiteHost(): string {
  return getRuntimeConfig().siteHost;
}
