plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "eu.isaacdev.dozer"
    compileSdk = 35
    defaultConfig {
        applicationId = "eu.isaacdev.dozer"
        minSdk = 29
        targetSdk = 35
        versionCode = 2
        versionName = "1.1"
        ndk { abiFilters += listOf("arm64-v8a") }
    }
    signingConfigs {
        create("release") {
            storeFile = file("../dozer-release.jks")
            storePassword = System.getenv("DOZER_KS_PASS")
            keyAlias = "dozer"
            keyPassword = System.getenv("DOZER_KS_PASS")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { jniLibs { useLegacyPackaging = true } }
    androidResources { noCompress += listOf("onnx") }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
}
