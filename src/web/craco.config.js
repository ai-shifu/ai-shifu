const cracoAlias = require('craco-alias');
const NodePolyfillPlugin = require('node-polyfill-webpack-plugin');

module.exports = {
  plugins: [
    {
      plugin: cracoAlias,
      options: {
        baseUrl: './src',
        source: 'tsconfig',
        tsConfigPath: './tsconfig.json',
      },
    },
  ],
  devServer: {
    client: {
      overlay: {
        errors: true,
        warnings: false,
        runtimeErrors: false,
      },
    },
  },
  webpack: {
    configure: (webpackConfig) => {
      const oneOfRuleIndex = webpackConfig.module.rules.findIndex(
        (rule) => rule.oneOf,
      );

      if (oneOfRuleIndex >= 0) {
        webpackConfig.module.rules[oneOfRuleIndex].oneOf.unshift({
          test: /\.md$/,
          use: 'raw-loader',
        });

        const tsRule = webpackConfig.module.rules[oneOfRuleIndex].oneOf.find(
          (rule) => rule.test && rule.test.toString().includes('tsx'),
        );

        if (tsRule) {
          webpackConfig.module.rules[oneOfRuleIndex].oneOf =
            webpackConfig.module.rules[oneOfRuleIndex].oneOf.filter(
              (rule) => !(rule.test && rule.test.toString().includes('tsx')),
            );
        }

        webpackConfig.module.rules[oneOfRuleIndex].oneOf.unshift({
          test: /\.(ts|tsx)$/,
          exclude: /node_modules/,
          use: {
            loader: 'esbuild-loader',
            options: {
              loader: 'tsx',
              target: 'es2015',
              tsconfigRaw: require('./tsconfig.json'),
            },
          },
        });
      }

      // ios 16- don't support look behind
      webpackConfig.module.rules.push({
        test: /\.js$/,
        use: [
          {
            loader: 'string-replace-loader',
            options: {
              multiple: [
                {
                  search: '?<=\\\\s|',
                  replace: '',
                },
                {
                  search: '?<=^',
                  replace: '^',
                },
                {
                  search: '?<="',
                  replace: '?="',
                },
              ],
            },
          },
        ],
      });

      if (process.env.NODE_ENV === 'production') {
        webpackConfig.devtool = false;
      }

      webpackConfig.resolve = {
        ...webpackConfig.resolve,
        fallback: {
          ...webpackConfig.resolve?.fallback,
          util: require.resolve('util/'),
          stream: require.resolve('stream-browserify'),
          buffer: require.resolve('buffer/'),
          process: false,
          querystring: require.resolve('querystring-es3'),
          url: require.resolve('url/'),
        },
      };

      const webpack = require('webpack');
      webpackConfig.plugins = [
        ...webpackConfig.plugins,
        new NodePolyfillPlugin(),
        new webpack.ProvidePlugin({
          Buffer: ['buffer', 'Buffer'],
        }),
      ];

      return webpackConfig;
    },
  },
};
