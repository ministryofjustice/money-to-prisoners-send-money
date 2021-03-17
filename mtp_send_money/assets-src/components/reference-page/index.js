'use strict';

export var Reference = {
  init: function () {
    $('.mtp-reference-actions__print').click(function (e) {
      e.preventDefault();
      try {
        window.print();
      } catch (error) {
        if (typeof Sentry !== 'undefined') {
          Sentry.captureException(error);
        }
      }
    });
  }
};
