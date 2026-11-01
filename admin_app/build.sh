#!/usr/bin/env bash
# Builds the admin panel app (WebView wrapper) without Gradle: aapt2 + javac + d8 + zipalign + apksigner.
# Usage: SDK=<android-sdk> KEYSTORE=<debug.keystore> ./build.sh [out.apk]
set -euo pipefail
cd "$(dirname "$0")"
SDK=${SDK:?set SDK to the Android SDK path}
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
JAR=$(ls -d "$SDK"/platforms/android-* | sort -V | tail -1)/android.jar
OUT=${1:-../build/uralia-admin.apk}
W=$(mktemp -d)
"$BT/aapt2" compile --dir res -o "$W/res.zip"
"$BT/aapt2" link -o "$W/base.apk" -I "$JAR" --manifest AndroidManifest.xml "$W/res.zip" --min-sdk-version 24 --target-sdk-version 35
mkdir -p "$W/cls" "$W/dex"
javac -nowarn -source 8 -target 8 -bootclasspath "$JAR:$BT/core-lambda-stubs.jar" -d "$W/cls" $(find src -name '*.java') 2>&1 | grep -v "warning" || true
"$BT/d8" --min-api 24 --output "$W/dex" $(find "$W/cls" -name '*.class')
(cd "$W/dex" && zip -q "$W/base.apk" classes.dex)
"$BT/zipalign" -f -p 4 "$W/base.apk" "$W/aligned.apk"
mkdir -p "$(dirname "$OUT")"
"$BT/apksigner" sign --ks "${KEYSTORE:?set KEYSTORE}" --ks-pass pass:android --key-pass pass:android --out "$OUT" "$W/aligned.apk"
rm -rf "$W"
echo "built $OUT"
