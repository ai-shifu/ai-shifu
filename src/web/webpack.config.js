const path = require('path');
const NodePolyfillPlugin = require('node-polyfill-webpack-plugin');

module.exports = {
  mode: process.env.NODE_ENV === 'production' ? 'production' : 'development',
  entry: './src/index.tsx',
  output: {
    path: path.resolve(__dirname, 'build'),
    filename: 'bundle.js',
  },
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
    fallback: {
      util: require.resolve('util/'),
      stream: require.resolve('stream-browserify'),
      buffer: require.resolve('buffer/'),
      process: false,
      querystring: require.resolve('querystring-es3'),
      url: require.resolve('url/'),
    },
    alias: {
      '@Assets': path.resolve(__dirname, 'src/Assets'),
      '@Components': path.resolve(__dirname, 'src/Components'),
      '@pages': path.resolve(__dirname, 'src/pages'),
      '@assets': path.resolve(__dirname, 'src/assets'),
      '@images': path.resolve(__dirname, 'src/assets/img'),
      '@icons': path.resolve(__dirname, 'src/assets/icons'),
      '@constants': path.resolve(__dirname, 'src/constants'),
      '@Service': path.resolve(__dirname, 'src/Service'),
      '@Utils': path.resolve(__dirname, 'src/Utils'),
      '@stores': path.resolve(__dirname, 'src/stores'),
      '@Api': path.resolve(__dirname, 'src/Api'),
      '@ShiNiang': path.resolve(__dirname, 'src/ShiNiang'),
      Assets: path.resolve(__dirname, 'src/Assets'),
      Components: path.resolve(__dirname, 'src/Components'),
      constants: path.resolve(__dirname, 'src/constants'),
      Service: path.resolve(__dirname, 'src/Service'),
      Utils: path.resolve(__dirname, 'src/Utils'),
      stores: path.resolve(__dirname, 'src/stores'),
      Api: path.resolve(__dirname, 'src/Api'),
      ShiNiang: path.resolve(__dirname, 'src/ShiNiang'),
    },
  },
  module: {
    rules: [
      {
        test: /\.md$/,
        use: 'raw-loader',
      },
      {
        test: /\.(ts|tsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'esbuild-loader',
          options: {
            loader: 'tsx',
            target: 'es2015',
          },
        },
      },
      {
        test: /\.(js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env', '@babel/preset-react'],
          },
        },
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
      {
        test: /\.scss$/,
        use: ['style-loader', 'css-loader', 'sass-loader'],
      },
      {
        test: /\.(png|jpg|gif|svg)$/,
        use: {
          loader: 'file-loader',
          options: {
            name: '[name].[ext]',
            outputPath: 'images/',
          },
        },
      },
    ],
  },
  plugins: [new NodePolyfillPlugin()],
};
