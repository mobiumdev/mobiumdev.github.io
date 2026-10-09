// @ts-check
import {themes as prismThemes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'Mobium',
  tagline: 'Mobile app automation for AI agents and humans',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://mobiumdev.github.io',
  baseUrl: '/',
  organizationName: 'mobiumdev',
  projectName: 'mobiumdev.github.io',
  deploymentBranch: 'gh-pages',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',
  markdown: {
    // Pages generated from source are CommonMark, so a `<` or a `{` in a doc
    // comment is text, not JSX.
    format: 'detect',
    hooks: {onBrokenMarkdownLinks: 'throw', onBrokenMarkdownImages: 'throw'},
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      image: 'img/mobium-icon-512.png',
      colorMode: {
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: 'Mobium',
        logo: {
          alt: 'Mobium',
          src: 'img/logo.svg',
        },
        items: [
          {to: '/quickstart', label: 'Quick start', position: 'left'},
          {to: '/guides', label: 'Guides', position: 'left'},
          {to: '/reference', label: 'Reference', position: 'left'},
          {
            type: 'dropdown',
            label: 'Surfaces',
            position: 'left',
            items: [
              {to: '/reference/cli', label: 'CLI'},
              {to: '/reference/mcp', label: 'MCP'},
              {to: '/reference/python', label: 'Python'},
              {to: '/reference/javascript', label: 'JavaScript'},
              {to: '/reference/go', label: 'Go'},
              {to: '/reference/java', label: 'Java'},
              {to: '/reference/dotnet', label: '.NET'},
            ],
          },
          {
            href: 'https://github.com/mobiumdev/mobium',
            label: 'GitHub',
            position: 'right',
          },
        ],
      },
      footer: {
        style: 'dark',
        links: [
          {
            title: 'Docs',
            items: [
              {label: 'Introduction', to: '/'},
              {label: 'Quick start', to: '/quickstart'},
              {label: 'Reference', to: '/reference'},
            ],
          },
          {
            title: 'Source',
            items: [
              {label: 'mobiumdev/mobium', href: 'https://github.com/mobiumdev/mobium'},
              {label: 'MobiumApp', href: 'https://github.com/mobiumdev/mobium-app'},
              {label: 'This site', href: 'https://github.com/mobiumdev/mobiumdev.github.io'},
            ],
          },
        ],
        copyright: `Mobium is licensed under the Apache License 2.0. Built with Docusaurus.`,
      },
      prism: {
        theme: prismThemes.github,
        darkTheme: prismThemes.dracula,
        additionalLanguages: ['java', 'csharp', 'bash', 'json'],
      },
    }),
};

export default config;
