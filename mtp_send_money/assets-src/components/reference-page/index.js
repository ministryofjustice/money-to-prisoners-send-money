/* globals Sentry */
'use strict';

export var Reference = {
  init: function () {
    $('.mtp-reference-actions__print').click(function (e) {
      e.preventDefault();
      try {
        window.print();
      } catch (error) {
        if (Sentry !== undefined) {
          Sentry.captureException(error);
        }
      }
    });
  }
};
