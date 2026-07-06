/** @type {import('@commitlint/types').UserConfig} */
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Scopes are free-form (history uses dfm, viewport, engine, inspector, ...).
    'body-max-line-length': [0, 'always'], // release-please bodies can be long
  },
};
