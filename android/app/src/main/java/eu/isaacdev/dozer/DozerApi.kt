package eu.isaacdev.dozer

import android.util.Base64
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class Reply(val transcript: String, val reply: String, val audio: ByteArray?)

class DozerApi(private val prefs: Prefs) {
    private fun open(path: String, method: String, ctype: String?): HttpURLConnection {
        val c = URL(prefs.server + path).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 10_000
        c.readTimeout = 240_000                       // brain cold start can take a while
        c.setRequestProperty("Authorization", "Bearer ${prefs.token}")
        if (ctype != null) { c.doOutput = true; c.setRequestProperty("Content-Type", ctype) }
        return c
    }

    private fun parse(c: HttpURLConnection): Reply {
        val code = c.responseCode
        if (code == 401) throw IllegalStateException("Token rejected (401) — check the token in Dozer settings")
        if (code !in 200..299) throw IllegalStateException("Server error $code")
        val j = JSONObject(c.inputStream.bufferedReader().readText())
        val b64 = j.optString("audio_wav_b64", "")
        return Reply(j.optString("transcript"), j.optString("reply"),
            if (b64.isNotEmpty() && b64 != "null") Base64.decode(b64, Base64.DEFAULT) else null)
    }

    fun voice(wav: ByteArray): Reply {
        val c = open("/api/voice", "POST", "audio/wav")
        c.outputStream.use { it.write(wav) }
        return parse(c)
    }

    fun text(text: String): Reply {
        val c = open("/api/text", "POST", "application/json")
        c.outputStream.use { it.write(JSONObject().put("text", text).put("speak", true).toString().toByteArray()) }
        return parse(c)
    }

    fun ping(): String {
        val c = open("/api/ping", "GET", null)
        if (c.responseCode == 401) return "token rejected"
        val j = JSONObject(c.inputStream.bufferedReader().readText())
        return if (j.optBoolean("brain")) "connected · brain online" else "connected · brain offline"
    }
}
