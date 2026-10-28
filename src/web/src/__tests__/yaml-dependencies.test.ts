import { createRequire } from 'node:module';

type YamlLoader = {
  load: (source: string, options?: { maxTotalMergeKeys?: number }) => unknown;
  safeLoad?: (source: string) => unknown;
};

// Resolve from the consumer: the coverage tools must keep the 3.x API.
const consumers = [['coverage', '@istanbuljs/load-nyc-config']] as const;

describe.each(consumers)('%s YAML dependency', (_name, consumer) => {
  const yaml: YamlLoader = createRequire(require.resolve(consumer))('js-yaml');

  it('preserves anchors, merge precedence, scalars and ordered maps', () => {
    expect(
      yaml.load(
        'defaults: &defaults {enabled: true, count: 2}\n' +
          'lesson: {<<: *defaults, count: 3, title: "Lesson"}\n' +
          'order: !!omap [{first: 1}, {second: 2}]\n',
      ),
    ).toEqual({
      defaults: { enabled: true, count: 2 },
      lesson: { enabled: true, count: 3, title: 'Lesson' },
      order: [{ first: 1 }, { second: 2 }],
    });
    expect(() =>
      yaml.load('!!omap [{duplicate: 1}, {duplicate: 2}]'),
    ).toThrow();
  });

  it('counts empty merge sources against the CPU budget', () => {
    const source =
      `sources: &sources [${Array(20).fill('{}').join(',')}]\n` +
      'targets:\n  - <<: *sources\n  - <<: *sources\n';

    expect(() => yaml.load(source, { maxTotalMergeKeys: 10 })).toThrow(
      /merge/i,
    );
    const longSequence =
      `sources: &sources [${Array(101).fill('{}').join(',')}]\n` +
      'target: {<<: *sources}\n';
    expect(() => yaml.load(longSequence)).toThrow(/merge/i);
  });

  it('bounds chained merges while allowing ordinary merges', () => {
    const source = ['a0: &a0 {k0: 0}'];
    for (let index = 1; index < 20; index += 1) {
      source.push(
        `a${index}: &a${index} {<<: *a${index - 1}, k${index}: ${index}}`,
      );
    }
    expect(() =>
      yaml.load(source.join('\n'), { maxTotalMergeKeys: 10 }),
    ).toThrow(/merge/i);
    expect(yaml.load('a: &a {value: 1}\nb: {<<: *a}\n')).toEqual({
      a: { value: 1 },
      b: { value: 1 },
    });
  });

  if (consumer === '@istanbuljs/load-nyc-config') {
    it('retains the safeLoad API used by coverage configuration', () => {
      expect(yaml.safeLoad?.('include: [src/**/*.ts]\n')).toEqual({
        include: ['src/**/*.ts'],
      });
    });
  }
});
