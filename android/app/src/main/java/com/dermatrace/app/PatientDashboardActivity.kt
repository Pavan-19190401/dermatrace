package com.dermatrace.app

import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.dermatrace.app.databinding.ActivityPatientDashboardBinding
import com.dermatrace.app.network.ApiClient
import java.io.File

class PatientDashboardActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPatientDashboardBinding
    private var session1Path: String? = null
    private var sessionNPath: String? = null
    private var currentCapturingSession: Int = 1

    private val cameraLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK && result.data != null) {
            val capturedPath = result.data?.getStringExtra("CAPTURED_IMAGE_PATH")
            if (capturedPath != null) {
                if (currentCapturingSession == 1) {
                    session1Path = capturedPath
                    val bmp = BitmapFactory.decodeFile(capturedPath)
                    if (bmp != null) binding.ivSession1Thumb.setImageBitmap(bmp)
                    binding.tvSession1Status.text = "Captured"
                    Toast.makeText(this, "Session 1 (Baseline) photo saved!", Toast.LENGTH_SHORT).show()
                } else {
                    sessionNPath = capturedPath
                    val bmp = BitmapFactory.decodeFile(capturedPath)
                    if (bmp != null) binding.ivSessionNThumb.setImageBitmap(bmp)
                    binding.tvSessionNStatus.text = "Captured"
                    Toast.makeText(this, "Session N (Follow-up) photo saved!", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPatientDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.tvPatientGreeting.text = "🌸 Hello, ${ApiClient.currentUserEmail.substringBefore('@')}"

        setupSessionButtons()
        setupLogout()
    }

    private fun setupSessionButtons() {
        // Capture Session 1 (Baseline)
        binding.btnCaptureSession1.setOnClickListener {
            currentCapturingSession = 1
            val intent = Intent(this, CameraActivity::class.java).apply {
                putExtra("EXTRA_SESSION_TITLE", "Session 1 (Baseline)")
            }
            cameraLauncher.launch(intent)
        }

        // Capture Session N (Follow-up) with Ghost overlay from Session 1
        binding.btnCaptureSessionN.setOnClickListener {
            currentCapturingSession = 2
            val intent = Intent(this, CameraActivity::class.java).apply {
                putExtra("EXTRA_SESSION_TITLE", "Session N (Follow-up)")
                if (!session1Path.isNullOrEmpty()) {
                    putExtra("EXTRA_GHOST_PATH", session1Path)
                }
            }
            cameraLauncher.launch(intent)
        }

        // Compare Session 1 vs Session N
        binding.btnRunCompareSessions.setOnClickListener {
            val intent = Intent(this, CompareActivity::class.java).apply {
                putExtra("EXTRA_SESSION_1_PATH", session1Path)
                putExtra("EXTRA_SESSION_N_PATH", sessionNPath)
            }
            startActivity(intent)
        }
    }

    private fun setupLogout() {
        binding.btnLogout.setOnClickListener {
            ApiClient.authToken = null
            ApiClient.activeRole = "client"
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }
}
