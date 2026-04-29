/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // B站浅色主题
        bg: {
          primary: '#F4F5F7',
          secondary: '#FFFFFF',
          card: '#FFFFFF',
          header: '#FFFFFF',
        },
        bilibili: {
          blue: '#00A1D6',
          pink: '#FB7299',
          purple: '#E89ABE',
          dark: '#18191C',
          gray: '#99A2A4',
          lightgray: '#E3E5E7',
          border: '#E3E5E7',
        },
        accent: {
          blue: '#00A1D6',
          pink: '#FB7299',
          green: '#4CB026',
          yellow: '#FFA502',
          orange: '#FF5C38',
        },
        text: {
          primary: '#18191C',
          secondary: '#61666D',
          tertiary: '#99A2A4',
        },
        border: {
          light: '#E3E5E7',
          card: '#F0F1F2',
        }
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 2px 12px rgba(0,0,0,0.08)',
        'card-hover': '0 4px 20px rgba(0,0,0,0.12)',
      },
      borderRadius: {
        xl: '12px',
        '2xl': '16px',
      }
    },
  },
  plugins: [],
}
