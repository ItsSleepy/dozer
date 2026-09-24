package eu.isaacdev.dozer

import ai.picovoice.porcupine.Porcupine
import ai.picovoice.porcupine.PorcupineManager
import ai.picovoice.porcupine.PorcupineManagerCallback
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.os.IBinder
import android.os.PowerManager
import android.speech.tts.TextToSpeech
import androidx.core.app.NotificationCompat
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class DozerService : Service() {
    companion object {
        const val ACTION_START = "start"
        const val ACTION_STOP = "stop"
        const val ACTION_TALK = "talk"
        private const val CHANNEL = "dozer"
        private const val NOTIF_ID = 1
        var running = false
        var onStatus: ((String) -> Unit)? = null
        var onExchange: ((String, String) -> Unit)? = null
        fun wakeWordFile(ctx: Context) = File(ctx.filesDir, "hey_dozer.ppn")
    }

    private lateinit var prefs: Prefs
    private lateinit var api: DozerApi
    private val worker = Executors.newSingleThreadExecutor()
    private var porcupine: PorcupineManager? = null
    private var tts: TextToSpeech? = null
    private var busy = false
    private var wakeWordLabel = "none"

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        api = DozerApi(prefs)
        tts = TextToSpeech(this) {}
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Dozer", NotificationManager.IMPORTANCE_LOW))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { prefs.listening = false; stopSelf(); return START_NOT_STICKY }
            ACTION_TALK -> { ensureForeground(); worker.execute { converse() } }
            else -> { ensureForeground(); worker.execute { startWakeWord() } }
        }
        return START_STICKY
    }

    private fun ensureForeground() {
        if (running) return
        running = true
        startForeground(NOTIF_ID, notification("Starting…"), ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val talk = PendingIntent.getService(this, 1, Intent(this, DozerService::class.java).setAction(ACTION_TALK),
            PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 2, Intent(this, DozerService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("Dozer")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(0, "Talk", talk)
            .addAction(0, "Stop", stop)
            .build()
    }

    private fun status(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIF_ID, notification(text))
        onStatus?.invoke(text)
    }

    // ── wake word ──────────────────────────────────────────────────────────
    private fun startWakeWord() {
        if (prefs.picoKey.isBlank()) { status("Add your Picovoice AccessKey to enable the wake word"); return }
        try {
            porcupine?.delete()
            val cb = PorcupineManagerCallback { worker.execute { onWake() } }
            val b = PorcupineManager.Builder().setAccessKey(prefs.picoKey).setSensitivity(prefs.sensitivity)
            val custom = wakeWordFile(this)
            if (custom.exists()) { b.setKeywordPath(custom.absolutePath); wakeWordLabel = "\"Hey Dozer\"" }
            else { b.setKeyword(Porcupine.BuiltInKeyword.JARVIS); wakeWordLabel = "\"Jarvis\" (import Hey Dozer to switch)" }
            porcupine = b.build(applicationContext, cb)
            porcupine?.start()
            prefs.listening = true
            status("Listening for $wakeWordLabel")
        } catch (e: Exception) {
            status("Wake word error: ${e.message}")
        }
    }

    private fun onWake() {
        if (busy) return
        try { porcupine?.stop() } catch (_: Exception) {}
        converse()
        try { porcupine?.start(); status("Listening for $wakeWordLabel") } catch (_: Exception) {}
    }

    // ── one conversation (with follow-ups when Dozer asks a question) ─────
    private fun converse() {
        if (busy) return
        busy = true
        val pm = getSystemService(PowerManager::class.java)
        val lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dozer:converse").apply { acquire(5 * 60_000L) }
        val am = getSystemService(AudioManager::class.java)
        val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()).build()
        am.requestAudioFocus(focus)
        try {
            var turns = 0
            while (turns++ < 4) {
                beep(ToneGenerator.TONE_PROP_BEEP)
                status("Listening…")
                val wav = Recorder.recordUtterance()
                if (wav == null) { beep(ToneGenerator.TONE_PROP_NACK); break }
                status("Thinking…")
                val r = try { api.voice(wav) } catch (e: Exception) { speakLocal("I can't reach Dozer. ${e.message ?: ""}"); break }
                onExchange?.invoke(r.transcript, r.reply)
                status("“${r.transcript}”")
                if (r.audio != null) play(r.audio) else speakLocal(r.reply)
                if (!r.reply.trim().endsWith("?")) break         // Dozer asked something -> listen again
            }
        } finally {
            am.abandonAudioFocusRequest(focus)
            if (lock.isHeld) lock.release()
            busy = false
            if (porcupine == null) status("Ready — tap Talk")
        }
    }

    private fun beep(tone: Int) {
        try {
            ToneGenerator(AudioManager.STREAM_MUSIC, 70).apply { startTone(tone, 150); Thread.sleep(200); release() }
        } catch (_: Exception) {}
    }

    private fun play(wav: ByteArray) {
        val f = File(cacheDir, "reply.wav").apply { writeBytes(wav) }
        val done = CountDownLatch(1)
        val mp = MediaPlayer().apply {
            setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            setDataSource(f.absolutePath)
            setOnCompletionListener { done.countDown() }
            setOnErrorListener { _, _, _ -> done.countDown(); true }
            prepare(); start()
        }
        done.await(120, TimeUnit.SECONDS)
        mp.release()
    }

    private fun speakLocal(text: String) {
        val done = CountDownLatch(1)
        tts?.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
            override fun onStart(id: String?) {}
            override fun onDone(id: String?) { done.countDown() }
            @Deprecated("Deprecated in Java") override fun onError(id: String?) { done.countDown() }
        })
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "dozer")
        done.await(20, TimeUnit.SECONDS)
    }

    override fun onDestroy() {
        running = false
        try { porcupine?.stop(); porcupine?.delete() } catch (_: Exception) {}
        porcupine = null
        tts?.shutdown()
        worker.shutdownNow()
        onStatus?.invoke("Stopped")
        super.onDestroy()
    }
}
