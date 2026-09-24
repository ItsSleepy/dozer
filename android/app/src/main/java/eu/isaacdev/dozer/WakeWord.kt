package eu.isaacdev.dozer

import android.annotation.SuppressLint
import android.content.res.AssetManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.KeywordSpotter
import com.k2fsa.sherpa.onnx.KeywordSpotterConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig

/** Offline "Hey Dozer" detector (sherpa-onnx keyword spotting, no account, nothing leaves the phone). */
class WakeWord(assets: AssetManager, threshold: Float) {
    private val spotter = KeywordSpotter(
        assetManager = assets,
        config = KeywordSpotterConfig(
            featConfig = FeatureConfig(sampleRate = 16000, featureDim = 80),
            modelConfig = OnlineModelConfig(
                transducer = OnlineTransducerModelConfig(
                    encoder = "kws/encoder.onnx", decoder = "kws/decoder.onnx", joiner = "kws/joiner.onnx"),
                tokens = "kws/tokens.txt", modelType = "zipformer2", numThreads = 1, provider = "cpu"),
            keywordsFile = "kws/keywords.txt",
            keywordsThreshold = threshold,
            keywordsScore = 1.0f,
        ),
    )
    @Volatile private var running = false
    private var thread: Thread? = null

    @SuppressLint("MissingPermission")
    fun start(onDetected: () -> Unit) {
        if (running) return
        running = true
        thread = Thread {
            val rate = 16000
            val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, rate,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, rate))
            val stream = spotter.createStream()
            val buf = ShortArray(rate / 10)                     // 100 ms
            rec.startRecording()
            try {
                while (running) {
                    val n = rec.read(buf, 0, buf.size)
                    if (n <= 0) continue
                    val f = FloatArray(n) { buf[it] / 32768f }
                    stream.acceptWaveform(f, rate)
                    while (spotter.isReady(stream)) {
                        spotter.decode(stream)
                        if (spotter.getResult(stream).keyword.isNotBlank()) {
                            spotter.reset(stream)
                            running = false
                            break
                        }
                    }
                    if (!running) { rec.stop(); rec.release(); stream.release(); onDetected(); return@Thread }
                }
            } finally {
                try { rec.stop() } catch (_: Exception) {}
                try { rec.release() } catch (_: Exception) {}
            }
            stream.release()
        }.apply { name = "dozer-wakeword"; start() }
    }

    fun stop() {
        running = false
        thread?.join(1500)
        thread = null
    }

    fun release() { stop(); spotter.release() }
}
