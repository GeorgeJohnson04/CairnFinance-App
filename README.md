# Cairn for Android and iOS

This folder is the native shell for Cairn, built with
[Capacitor](https://capacitorjs.com/). It wraps the Cairn web app in a real
Android and iOS project you can sign and submit to Google Play and the App
Store.

## How this works (read this first)

Cairn's backend is Python and Flask. A phone cannot run that server inside the
app, so the native shell **loads Cairn from a server you host**. The flow is:

```
[ iOS / Android app ]  ->  https://your-domain.com  ->  [ Flask + SQLite ]
```

Two consequences worth understanding before you invest in the store path:

1. **You need to deploy the server first.** See `DEPLOYMENT.md` in the project
   root. The mobile app is unusable without a reachable HTTPS URL.
2. **The "runs only on your device" promise changes.** On desktop the .exe
   keeps everything local. Once phones connect to a shared server, that server
   holds the data. Say this accurately in your store listing and privacy
   policy, or you will have a problem at review time.

## Prerequisites

| Target | You need | Cost |
|---|---|---|
| Android | Android Studio (includes the SDK and an emulator) | Google Play: $25 one time |
| iOS | A **Mac** with Xcode and CocoaPods | Apple Developer: $99 per year |

iOS cannot be built on Windows. The `ios/` project in this folder is valid and
version-controlled, but you must open and build it on a Mac.

## Point the app at your server

The server URL is read from an environment variable at sync time, so you never
hardcode it:

```powershell
# Windows PowerShell
$env:CAIRN_SERVER_URL = "https://app.yourdomain.com"
npx cap sync
```

```bash
# macOS / Linux
export CAIRN_SERVER_URL=https://app.yourdomain.com
npx cap sync
```

If you leave it unset, the app targets `http://10.0.2.2:5000`, which is how the
Android emulator reaches the dev server running on your computer. That is for
development only. Production builds must use HTTPS, otherwise the session
cookie (marked `Secure`) will not persist and logins will silently fail.

## Build and run

```bash
npm install
npx cap sync            # copies config + web assets into the native projects
npm run open:android    # opens Android Studio
npm run open:ios        # opens Xcode (Mac only)
```

From Android Studio: **Run** to test on an emulator or device, then
**Build > Generate Signed Bundle / APK > Android App Bundle (.aab)** for Play.

From Xcode: pick a simulator to test, then **Product > Archive** and use the
Organizer to upload to App Store Connect.

## App icons and splash screens

Source art lives in `assets/` (`icon.png`, `splash.png`, `splash-dark.png`),
generated from the Cairn logo. Regenerate every platform-specific size with:

```bash
npm run icons
```

That rewrites the icon and splash sets inside `android/` and `ios/`.

## Store submission checklist

Both stores require these for a finance app:

- [ ] A reachable **privacy policy URL**, stating what you collect, where it is
      stored, and that you do not sell data. Both stores reject finance apps
      without one.
- [ ] Google Play **Data safety** form filled in (declare account data and
      financial info, and whether it is encrypted in transit).
- [ ] Apple **App Privacy** questionnaire in App Store Connect.
- [ ] Screenshots at the required sizes (Play: phone plus 7in and 10in tablet;
      Apple: 6.7in and 6.5in iPhone at minimum).
- [ ] The "not financial advice" disclaimer visible in the app and in the
      listing description. Cairn already shows it on every page.
- [ ] Account deletion available in-app. Apple requires this for any app with
      accounts. Cairn has it under Settings > Danger zone.

## The main App Store risk, stated plainly

Apple **App Review Guideline 4.2 (Minimum Functionality)** rejects apps that
are essentially a website in a native wrapper. A Capacitor shell that only
loads a URL is exactly the shape reviewers look for. Google Play is far more
permissive here; Apple is not.

To reduce the risk, add capabilities a website cannot provide. In rough order
of effort to payoff:

1. **Biometric unlock** (Face ID / fingerprint) before showing the portfolio.
   Cheap to add, very obviously native, and a natural fit for a finance app.
2. **Offline caching** so the last dashboard renders without a connection.
3. **Push notifications**, for example a monthly "log your dividends" nudge.
4. **A home screen widget** showing total portfolio value.

Adding at least biometric unlock before submitting to Apple is strongly
recommended. Google Play should accept the current build as is.

## Cheaper alternative: install it as a PWA

Cairn is already a Progressive Web App. Anyone can install it from the browser
with no store, no fees, and no review:

- **Android / Chrome:** open the site, then menu > *Add to Home screen*.
- **iOS / Safari:** open the site, then Share > *Add to Home Screen*.

That gives a home screen icon, a splash screen, and a standalone window with no
browser chrome. It is the fastest way to have Cairn on a phone, and it is worth
shipping first while you decide whether the store path is worth the cost.
