package eu.isaacdev.dozer

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {
    private lateinit var prefs: Prefs
    private lateinit var status: TextView
    private lateinit var log: TextView
    private lateinit var listenBtn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad * 2, pad, pad) }

        fun label(t: String) = TextView(this).apply { text = t; setPadding(0, pad, 0, 0) }
        fun field(v: String, secret: Boolean = false) = EditText(this).apply {
            setText(v); isSingleLine = true
            if (secret) inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        }
        fun button(t: String, f: (Button) -> Unit) = Button(this).apply { text = t; setOnClickListener { f(this) } }

        col.addView(TextView(this).apply { text = "Dozer"; textSize = 28f; setTypeface(null, Typeface.BOLD) })
        status = TextView(this).apply { text = if (DozerService.running) "Running" else "Stopped"; textSize = 16f }
        col.addView(status)

        listenBtn = button(if (prefs.listening) "Stop listening" else "Start listening") { toggleListening() }
        col.addView(listenBtn)
        col.addView(button("Talk now") { startSvc(DozerService.ACTION_TALK) })
        col.addView(TextView(this).apply { text = "Say \"Hey Dozer\" (also: \"Hi Dozer\", \"OK Dozer\"). Works offline on the phone — no account needed." })

        col.addView(label("Server"))
        val server = field(prefs.server); col.addView(server)
        col.addView(label("Dozer token"))
        val token = field(prefs.token, true); col.addView(token)
        col.addView(button("Save") {
            prefs.server = server.text.toString(); prefs.token = token.text.toString()
            Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
            if (DozerService.running && prefs.listening) startSvc(DozerService.ACTION_START)
        })
        col.addView(button("Test connection") {
            Thread {
                val r = try { DozerApi(prefs).ping() } catch (e: Exception) { "failed: ${e.message}" }
                runOnUiThread { status.text = "Server: $r" }
            }.start()
        })
        col.addView(button("Wake word sensitivity: " + sensLabel()) {
            prefs.sensitivity = when (prefs.sensitivity) { 0.25f -> 0.15f; 0.15f -> 0.35f; else -> 0.25f }
            (it as Button).text = "Wake word sensitivity: " + sensLabel()
            if (DozerService.running && prefs.listening) {
                startService(Intent(this, DozerService::class.java).setAction(DozerService.ACTION_STOP))
                window.decorView.postDelayed({ startSvc(DozerService.ACTION_START) }, 800)
            }
        })
        col.addView(button("Allow running in background (battery)") {
            val pm = getSystemService(PowerManager::class.java)
            if (pm.isIgnoringBatteryOptimizations(packageName)) Toast.makeText(this, "Already allowed", Toast.LENGTH_SHORT).show()
            else startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        })

        col.addView(label("Last exchange"))
        log = TextView(this).apply { setTextIsSelectable(true) }
        col.addView(log)

        setContentView(ScrollView(this).apply { addView(col) })
        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    override fun onResume() {
        super.onResume()
        DozerService.onStatus = { s -> runOnUiThread { status.text = s } }
        DozerService.onExchange = { you, dozer -> runOnUiThread { log.text = "You: $you\n\nDozer: $dozer" } }
    }

    override fun onPause() {
        DozerService.onStatus = null; DozerService.onExchange = null
        super.onPause()
    }

    private fun startSvc(action: String) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "Microphone permission needed", Toast.LENGTH_LONG).show()
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1); return
        }
        if (prefs.token.isBlank()) { Toast.makeText(this, "Enter the Dozer token first", Toast.LENGTH_LONG).show(); return }
        startForegroundService(Intent(this, DozerService::class.java).setAction(action))
    }

    private fun toggleListening() {
        if (prefs.listening && DozerService.running) {
            startService(Intent(this, DozerService::class.java).setAction(DozerService.ACTION_STOP))
            listenBtn.text = "Start listening"
        } else {
            startSvc(DozerService.ACTION_START)
            listenBtn.text = "Stop listening"
        }
    }

    private fun sensLabel() = when (prefs.sensitivity) { 0.15f -> "high"; 0.35f -> "low"; else -> "normal" }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data ?: return
        if (requestCode != 7 || resultCode != RESULT_OK) return
        contentResolver.openInputStream(uri)?.use { input ->
            DozerService.wakeWordFile(this).outputStream().use { input.copyTo(it) }
        }
        Toast.makeText(this, "Wake word imported", Toast.LENGTH_SHORT).show()
        if (DozerService.running && prefs.listening) startSvc(DozerService.ACTION_START)
    }
}
