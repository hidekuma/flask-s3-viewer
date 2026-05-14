module.exports = {
  content: ['../flask_s3_viewer/blueprints/templates/**/*.html'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Aptos',
          'IBM Plex Sans',
          'Segoe UI',
          'Helvetica Neue',
          'Noto Sans KR',
          'Apple SD Gothic Neo',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
};
