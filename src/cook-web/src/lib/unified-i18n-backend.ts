type BackendCallback = (error: Error | null, resources: any) => void;

type BackendMultiCallback = (
  error: Error | null,
  resources: Record<string, Record<string, unknown>> | false,
) => void;

type BackendOptions = {
  loadPath?: string;
  includeMetadata?: boolean;
  namespaces?: string[];
  requestOptions?: RequestInit;
};

const DEFAULT_OPTIONS: Required<BackendOptions> = {
  loadPath: '/api/i18n',
  includeMetadata: false,
  namespaces: [],
  requestOptions: { cache: 'no-cache' },
};

const setNestedValue = (
  target: Record<string, unknown>,
  keyPath: string,
  value: unknown,
) => {
  if (!keyPath) {
    return;
  }

  const segments = keyPath.split('.');
  let cursor: Record<string, unknown> = target;

  segments.forEach((segment, index) => {
    if (!segment) {
      return;
    }

    if (index === segments.length - 1) {
      cursor[segment] = value;
      return;
    }

    if (!(segment in cursor) || typeof cursor[segment] !== 'object') {
      cursor[segment] = {};
    }

    cursor = cursor[segment] as Record<string, unknown>;
  });
};

class UnifiedI18nBackend {
  public static type = 'backend' as const;

  public type = UnifiedI18nBackend.type;

  private options: Required<BackendOptions> = DEFAULT_OPTIONS;

  private cache = new Map<string, Record<string, unknown>>();

  private pending = new Map<string, Promise<Record<string, unknown>>>();

  init(_services: unknown, options: BackendOptions = {}): void {
    this.options = {
      ...DEFAULT_OPTIONS,
      ...options,
      requestOptions: {
        ...DEFAULT_OPTIONS.requestOptions,
        ...options.requestOptions,
      },
    };
  }

  async read(language: string, namespace: string, callback: BackendCallback) {
    try {
      const resources = await this.loadLanguage(language);
      callback(null, resources[namespace] ?? {});
    } catch (error) {
      callback(error as Error, null);
    }
  }

  async readMulti(
    languages: string[],
    namespaces: string[],
    callback: BackendMultiCallback,
  ) {
    try {
      await Promise.all(languages.map(language => this.loadLanguage(language)));

      const bundled: Record<string, Record<string, unknown>> = {};
      languages.forEach(language => {
        const resources = this.cache.get(language) ?? {};
        bundled[language] = namespaces.reduce<Record<string, unknown>>(
          (acc, ns) => {
            acc[ns] = resources[ns] ?? {};
            return acc;
          },
          {},
        );
      });

      callback(null, bundled);
    } catch (error) {
      callback(error as Error, false);
    }
  }

  create(): void {}

  private async loadLanguage(language: string) {
    const cached = this.cache.get(language);
    if (cached) {
      return cached;
    }

    const pending = this.pending.get(language);
    if (pending) {
      return pending;
    }

    const loader = (async () => {
      const baseUrl = this.options.loadPath ?? DEFAULT_OPTIONS.loadPath;
      const url = new URL(baseUrl, window.location.origin);
      url.searchParams.set('lng', language);

      const namespacesToFetch = this.options.namespaces.length
        ? this.options.namespaces
        : DEFAULT_OPTIONS.namespaces;

      if (namespacesToFetch.length) {
        url.searchParams.set('ns', namespacesToFetch.join(','));
      }

      if (!this.options.includeMetadata) {
        url.searchParams.set('meta', 'false');
      }

      try {
        const response = await fetch(url.toString(), {
          ...this.options.requestOptions,
          headers: {
            'Content-Type': 'application/json',
            ...(this.options.requestOptions.headers ?? {}),
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to load i18n resources for ${language}`);
        }

        const payload = await response.json();
        const baseTranslations: Record<string, unknown> =
          payload.translations ?? payload;

        const legacyNamespace: Record<string, unknown> = {};
        Object.entries(baseTranslations).forEach(([namespace, value]) => {
          if (namespace !== 'translation') {
            setNestedValue(legacyNamespace, namespace, value);
          }
        });

        const translationsWithLegacy: Record<string, unknown> = {
          ...baseTranslations,
        };

        if (!('translation' in translationsWithLegacy)) {
          translationsWithLegacy.translation = legacyNamespace;
        }

        this.cache.set(language, translationsWithLegacy);
        return translationsWithLegacy;
      } finally {
        this.pending.delete(language);
      }
    })();

    this.pending.set(language, loader);
    return loader;
  }
}

export default UnifiedI18nBackend;
