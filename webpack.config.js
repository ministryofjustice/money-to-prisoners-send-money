/* jshint node: true */

var webpack = require('webpack');

module.exports = {
  entry: {
    app: './mtp_send_money/assets-src/javascripts/main.js'
  },
  output: {
    path: './mtp_send_money/assets/javascripts',
    filename: '[name].bundle.js'
  },
  module: {
    loaders: [
      { include: /\.json$/, loaders: ['json-loader'] }
    ],
    noParse: [
      /\.\/node_modules\/checked-polyfill\/checked-polyfill\.js$/
    ]
  },
  resolve: {
    root: [
      __dirname + '/node_modules'
    ],
    modulesDirectories: [
      './mtp_send_money/assets-src/javascripts/modules',
      'node_modules',
      'node_modules/money-to-prisoners-common/assets/javascripts/modules'
    ],
    extensions: ['', '.json', '.js']
  },
  plugins: [
    new webpack.optimize.DedupePlugin(),
    new webpack.ProvidePlugin({
      $: 'jquery',
      jQuery: 'jquery'
    })
  ],
  devtool: 'source-map'
};
