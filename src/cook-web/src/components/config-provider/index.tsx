'use client';
import React, { useContext, useEffect, useState } from 'react';
import { setRuntimeConfig } from '@/config/runtime-config';
import '@/i18n';

interface ConfigContextType {
  isLoaded: boolean;
}

const ConfigContext = React.createContext<ConfigContextType>({ isLoaded: false });

export function ConfigProvider({ children }: { children: React.ReactNode }) {
  const [isLoaded, setIsLoaded] = useState(false);
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await fetch('/api/config');
        const config = await response.json();
        await setRuntimeConfig(config);
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
  const context = useContext(ConfigContext);
  if (context === undefined) {
    throw new Error('useConfig must be used within a ConfigProvider');
  }
  return context;
}
