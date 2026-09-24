package eu.isaacdev.dozer

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/** Records 16 kHz mono PCM until the speaker goes quiet. Returns a WAV file, or null if nothing was said. */
object Recorder {
    private const val RATE = 16000

    @SuppressLint("MissingPermission")
    fun recordUtterance(maxMs: Int = 15000, silenceMs: Int = 1200, waitForSpeechMs: Int = 5000): ByteArray? {
        val minBuf = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, RATE))
        val pcm = ByteArrayOutputStream()
        val frame = ShortArray(RATE / 50)                  // 20 ms
        val bytes = ByteBuffer.allocate(frame.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        var noiseFloor = 300.0
        var heardSpeech = false
        var quietMs = 0
        var elapsed = 0
        rec.startRecording()
        try {
            while (elapsed < maxMs) {
                val n = rec.read(frame, 0, frame.size)
                if (n <= 0) continue
                elapsed += 20
                var sum = 0.0
                for (i in 0 until n) sum += frame[i].toDouble() * frame[i]
                val rms = sqrt(sum / n)
                if (elapsed <= 200) noiseFloor = maxOf(noiseFloor, rms * 1.5)      // calibrate on the first 200 ms
                val speaking = rms > noiseFloor * 2.2 && rms > 500
                if (speaking) { heardSpeech = true; quietMs = 0 } else quietMs += 20
                bytes.clear(); for (i in 0 until n) bytes.putShort(frame[i])
                pcm.write(bytes.array(), 0, n * 2)
                if (!heardSpeech && elapsed >= waitForSpeechMs) return null
                if (heardSpeech && quietMs >= silenceMs) break
            }
        } finally {
            rec.stop(); rec.release()
        }
        return if (heardSpeech) wav(pcm.toByteArray()) else null
    }

    private fun wav(pcm: ByteArray): ByteArray {
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()); h.putInt(36 + pcm.size); h.put("WAVE".toByteArray())
        h.put("fmt ".toByteArray()); h.putInt(16); h.putShort(1); h.putShort(1)
        h.putInt(RATE); h.putInt(RATE * 2); h.putShort(2); h.putShort(16)
        h.put("data".toByteArray()); h.putInt(pcm.size)
        return h.array() + pcm
    }
}
