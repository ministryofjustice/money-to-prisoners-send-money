/* globals require */

(function() {
  'use strict';

  var Mojular = require('mojular');

  Mojular
    .use([
      require('mojular-govuk-elements'),
      require('mojular-moj-elements'),
      require('dialog'),
      require('messages'),
      require('print'),
      require('polyfills'),
      require('unload'),
      require('help-popup')
    ])
    .init();

}());
