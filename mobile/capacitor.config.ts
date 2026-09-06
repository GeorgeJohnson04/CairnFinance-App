import type { CapacitorConfig } from '@capacitor/cli';

// Cairn is a Flask server app, so the native shell loads it over HTTPS from
// wherever you deploy it. Set CAIRN_SERVER_URL before running `npx cap sync`
// to point a build at a different instance:
//
//   Windows PowerShell:  $env:CAIRN_SERVER_URL="https://app.yourdomain.com"
//   macOS / Linux:       export CAIRN_SERVER_URL=https://app.yourdomain.com
//
// Leave it unset for local development against the dev server. Android maps
// 10.0.2.2 to your computer's localhost from inside the emulator.
const serverUrl = process.env.CAIRN_SERVER_URL || '';
const isDev = !serverUrl;

const config: CapacitorConfig = {
  appId: 'app.cairnfinance.mobile',
  appName: 'Cairn',
  webDir: 'www',
  server: {
    url: serverUrl || 'http://10.0.2.2:5000',
    // Plain HTTP is only tolerated for the local dev server. A production
    // build must be HTTPS, or session cookies marked Secure will not stick.
    cleartext: isDev,
    androidScheme: 'https',
  },
  ios: {
    contentInset: 'always',
    limitsNavigationsToAppBoundDomains: false,
  },
  android: {
    allowMixedContent: isDev,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 900,
      backgroundColor: '#faf8ff',
      androidSplashResourceName: 'splash',
      showSpinner: false,
    },
    StatusBar: {
      style: 'DEFAULT',
      backgroundColor: '#7c3aed',
    },
  },
};

export default config;
