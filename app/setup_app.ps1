# Echo mobile app - one-time platform scaffolding (Windows / PowerShell)
#
#   .\setup_app.ps1                       # generate android/ + ios/, patch permissions, pub get
#   .\setup_app.ps1 -ApiUrl http://192.168.1.7:8010 -Run
#
# Why this exists: app/ contains only lib/ and pubspec.yaml, so `flutter run`
# has no Android or iOS project to build. `flutter create` regenerates the
# missing platform folders without touching lib/, and this script then adds
# the microphone, location, and cleartext-HTTP settings the app needs -- the
# things a fresh `flutter create` does not know about.

param(
    [string]$ApiUrl = "",
    [switch]$Run,
    [switch]$SkipCreate
)

$ErrorActionPreference = "Stop"
$appDir = $PSScriptRoot

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    Write-Error "flutter is not on PATH. Install the Flutter SDK first: https://docs.flutter.dev/get-started/install/windows"
}

Push-Location $appDir

if (-not $SkipCreate) {
    Write-Host "== Generating platform projects (android, ios) ==" -ForegroundColor Cyan
    flutter create --platforms=android,ios --project-name echo_app --org com.echo .
}

Write-Host "== Fetching packages ==" -ForegroundColor Cyan
flutter pub get

# ---------------------------------------------------------------- Android ---
$manifest = Join-Path $appDir "android\app\src\main\AndroidManifest.xml"
if (Test-Path $manifest) {
    Write-Host "== Patching AndroidManifest.xml ==" -ForegroundColor Cyan
    $xml = Get-Content $manifest -Raw

    $permissions = @(
        '<uses-permission android:name="android.permission.INTERNET"/>',
        '<uses-permission android:name="android.permission.RECORD_AUDIO"/>',
        '<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>',
        '<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>',
        '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE"/>',
        '<uses-permission android:name="android.permission.CALL_PHONE"/>'
    )
    $missing = $permissions | Where-Object { $xml -notmatch [regex]::Escape($_) }
    if ($missing) {
        $block = ($missing -join "`n    ")
        $xml = $xml -replace '(<manifest[^>]*>)', "`$1`n    $block"
    }

    # The backend is plain HTTP on a LAN address during development, which
    # Android blocks by default from API 28 onward.
    if ($xml -notmatch 'usesCleartextTraffic') {
        $xml = $xml -replace '(<application\b)', '$1 android:usesCleartextTraffic="true"'
    }

    # url_launcher needs to declare the dialer intent it queries (tel:112).
    if ($xml -notmatch '<queries>') {
        $queries = @"
    <queries>
        <intent>
            <action android:name="android.intent.action.DIAL" />
            <data android:scheme="tel" />
        </intent>
    </queries>
"@
        $xml = $xml -replace '(</manifest>)', "$queries`n`$1"
    }

    Set-Content -Path $manifest -Value $xml -Encoding utf8
    Write-Host "   permissions, cleartext HTTP, and the tel: query are in place." -ForegroundColor Green
}

# minSdk 23: the record package's WAV encoder and geolocator both need it.
$gradle = Join-Path $appDir "android\app\build.gradle"
$gradleKts = Join-Path $appDir "android\app\build.gradle.kts"
foreach ($file in @($gradle, $gradleKts)) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        $patched = $content -replace 'minSdk(Version)?\s*=?\s*(flutter\.minSdkVersion|\d+)', 'minSdk = 23'
        if ($patched -ne $content) {
            Set-Content -Path $file -Value $patched -Encoding utf8
            Write-Host "   minSdk set to 23 in $(Split-Path $file -Leaf)." -ForegroundColor Green
        }
    }
}

# -------------------------------------------------------------------- iOS ---
$plist = Join-Path $appDir "ios\Runner\Info.plist"
if (Test-Path $plist) {
    Write-Host "== Patching ios/Runner/Info.plist ==" -ForegroundColor Cyan
    $content = Get-Content $plist -Raw
    $entries = @{
        "NSMicrophoneUsageDescription" = "Echo listens for hazardous sounds such as gunshots, screams, and glass breaking so it can alert your emergency contacts."
        "NSLocationWhenInUseUsageDescription" = "Echo includes your location in the alert sent to your emergency contacts."
        "NSLocationAlwaysAndWhenInUseUsageDescription" = "Echo includes your location in the alert sent to your emergency contacts."
    }
    foreach ($key in $entries.Keys) {
        if ($content -notmatch [regex]::Escape($key)) {
            $entry = "	<key>$key</key>`n	<string>$($entries[$key])</string>"
            $content = $content -replace '(</dict>\s*</plist>)', "$entry`n`$1"
        }
    }
    if ($content -notmatch 'NSAppTransportSecurity') {
        $ats = @"
	<key>NSAppTransportSecurity</key>
	<dict>
		<key>NSAllowsLocalNetworking</key>
		<true/>
	</dict>
"@
        $content = $content -replace '(</dict>\s*</plist>)', "$ats`n`$1"
    }
    Set-Content -Path $plist -Value $content -Encoding utf8
    Write-Host "   microphone, location, and local-network entries are in place." -ForegroundColor Green
}

Pop-Location

Write-Host ""
Write-Host "Done. Start the backend first (.\run_local.ps1 from the repo root), then:" -ForegroundColor Green
if ($ApiUrl) {
    Write-Host "   flutter run --dart-define=ECHO_API_URL=$ApiUrl" -ForegroundColor Green
} else {
    Write-Host "   flutter run                                        # Android emulator (10.0.2.2)" -ForegroundColor Green
    Write-Host "   flutter run --dart-define=ECHO_API_URL=http://<your-lan-ip>:8010   # real phone" -ForegroundColor Green
}

if ($Run) {
    Push-Location $appDir
    if ($ApiUrl) { flutter run --dart-define=ECHO_API_URL=$ApiUrl } else { flutter run }
    Pop-Location
}
