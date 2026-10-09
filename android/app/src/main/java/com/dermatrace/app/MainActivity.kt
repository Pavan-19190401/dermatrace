package com.dermatrace.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.dermatrace.app.databinding.ActivityMainBinding
import com.dermatrace.app.network.ApiClient
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupRoleToggle()
        setupNavigation()
        checkBackendHealth()
        applyRoleUI()
    }

    private fun setupRoleToggle() {
        binding.btnToggleRole.setOnClickListener {
            // Toggle between Patient ("client") and Clinician ("admin")
            if (ApiClient.activeRole == "client") {
                ApiClient.activeRole = "admin"
                ApiClient.currentUserEmail = "admin@dermatrace.com"
                Toast.makeText(this, "🩺 Switched to Clinician Workstation", Toast.LENGTH_SHORT).show()
            } else {
                ApiClient.activeRole = "client"
                ApiClient.currentUserEmail = "patient@dermatrace.com"
                Toast.makeText(this, "👤 Switched to Patient View", Toast.LENGTH_SHORT).show()
            }
            applyRoleUI()
        }
    }

    private fun applyRoleUI() {
        if (ApiClient.isAdmin()) {
            binding.btnToggleRole.text = "🩺 Clinician (Admin)"
            binding.sectionPatient.visibility = View.GONE
            binding.sectionClinician.visibility = View.VISIBLE
            binding.tvHeaderSubtitle.text = "Clinical Workstation & Patient Triage"
        } else {
            binding.btnToggleRole.text = "👤 Patient"
            binding.sectionPatient.visibility = View.VISIBLE
            binding.sectionClinician.visibility = View.GONE
            binding.tvHeaderSubtitle.text = "Self-Monitoring & Guided Alignment"
        }
    }

    private fun setupNavigation() {
        // Patient Actions
        binding.btnOpenPatientCamera.setOnClickListener {
            startActivity(Intent(this, CameraActivity::class.java))
        }
        binding.btnOpenPatientCompare.setOnClickListener {
            startActivity(Intent(this, CompareActivity::class.java))
        }

        // Clinician Actions
        binding.btnOpenRegistry.setOnClickListener {
            startActivity(Intent(this, RegistryActivity::class.java))
        }
        binding.btnOpenMetrics.setOnClickListener {
            startActivity(Intent(this, ModelMetricsActivity::class.java))
        }
    }

    private fun checkBackendHealth() {
        lifecycleScope.launch {
            try {
                val response = ApiClient.service.getHealth()
                if (response.isSuccessful) {
                    binding.tvServerStatus.text = "● Connected to Deep Backend (Siamese Model Active)"
                    binding.tvServerStatus.setBackgroundColor(getColor(R.color.safe_green_bg))
                    binding.tvServerStatus.setTextColor(getColor(R.color.safe_green))
                } else {
                    binding.tvServerStatus.text = "○ Backend reachable (HTTP ${response.code()})"
                }
            } catch (e: Exception) {
                binding.tvServerStatus.text = "▲ Offline Mode (Local heuristic active)"
                binding.tvServerStatus.setBackgroundColor(getColor(R.color.warning_amber_bg))
                binding.tvServerStatus.setTextColor(getColor(R.color.warning_amber))
            }
        }
    }
}
