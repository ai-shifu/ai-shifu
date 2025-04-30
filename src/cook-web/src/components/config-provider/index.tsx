'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { setRuntimeConfig } from '@/config/runtime-config';
const ConfigContext = createContext<{ isLoaded: boolean }>({ isLoaded: false });
export function ConfigProvider({ children }: { children: React.ReactNode }) {
  const [isLoaded, setIsLoaded] = useState(false);
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await fetch('/api/config');
        const config = await response.json();
        await setRuntimeConfig(config);
        console.debug('Runtime config loaded:', config);
        setIsLoaded(true);
      } catch (error) {
        console.error('Failed to load runtime config:', error);
        setIsLoaded(true);
      }
    };

    loadConfig();
  }, []);

  if (!isLoaded) {
    return null;
  }

  return (
    <ConfigContext.Provider value={{ isLoaded }}>
      {children}
    </ConfigContext.Provider>
  );
}

export function useConfig() {
  return useContext(ConfigContext);
}
