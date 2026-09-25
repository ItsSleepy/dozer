package eu.isaacdev.dozer

import android.content.Context

class Prefs(ctx: Context) {
    private val p = ctx.getSharedPreferences("dozer", Context.MODE_PRIVATE)
    var server: String
        get() = p.getString("server", "https://dozer.isaac-dev.eu")!!
        set(v) = p.edit().putString("server", v.trim().trimEnd('/')).apply()
    var token: String
        get() = p.getString("token", "")!!
        set(v) = p.edit().putString("token", v.trim()).apply()
    var picoKey: String
        get() = p.getString("picoKey", "")!!
        set(v) = p.edit().putString("picoKey", v.trim()).apply()
    var sensitivity: Float
        get() = p.getFloat("sensitivity", 0.25f)
        set(v) = p.edit().putFloat("sensitivity", v).apply()
    var listening: Boolean
        get() = p.getBoolean("listening", false)
        set(v) = p.edit().putBoolean("listening", v).apply()
}
