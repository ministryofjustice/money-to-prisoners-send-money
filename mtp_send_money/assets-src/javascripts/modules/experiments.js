// A/B/N testing experiments
/* globals exports, require, $ */
'use strict';

var analytics = require('analytics');

exports.Experiments = {
  selector: '.js-experiment-context',

  init: function () {
    $(this.selector).each(function () {
      var context = ($(this).data('experiment-context') || '').split(',');
      if (context.length >= 2) {
        analytics.Analytics.send.apply(analytics.Analytics, context);
      }
    });
  }
};
