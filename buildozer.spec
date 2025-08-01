[app]
title = MyKivyApp
package.name = mykivyapp
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy,pyjnius
orientation = portrait

android.build_tools_version = 34.0.0
android.accept_sdk_license = True
android.api = 34
android.minapi = 21
android.ndk_api = 21
android.arch = arm64-v8a
android.enable_androidx = True
android.enable_multidex = True
android.permissions = INTERNET, MIDI

android.sdk_path = ~/.buildozer/android/platform/android-sdk
android.ndk_path = ~/.buildozer/android/platform/android-sdk/ndk/25.2.9519653
android.add_manifest_xml = True

p4a.branch = develop


[buildozer]
log_level = 2