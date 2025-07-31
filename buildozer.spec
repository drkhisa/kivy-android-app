[app]
title = MyKivyApp
package.name = mykivyapp
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy
orientation = portrait

[buildozer]
log_level = 2

[app]
android.api = 31
android.ndk_api = 21
android.arch = armeabi-v7a
android.sdk_path = ~/.buildozer/android/platform/android-sdk
android.ndk_path = /usr/local/lib/android/sdk/ndk/27.3.13750724