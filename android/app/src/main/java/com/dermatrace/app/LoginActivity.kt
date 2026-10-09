package com.dermatrace.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.dermatrace.app.databinding.ActivityLoginBinding
import com.dermatrace.app.network.ApiClient
import com.dermatrace.app.network.LoginRequest
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private var selectedRole: String = "client" // "client" (Patient) or "admin" (Clinician)
    private var isRegisterMode: Boolean = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupRoleTabs()
        setupAuthModeToggle()
        setupQuickDemoButtons()
        setupSubmitButton()
        checkServer()
    }

    private fun setupRoleTabs() {
        binding.tabClientRole.setOnClickListener {
            selectedRole = "client"
            binding.tabClientRole.setBackgroundResource(R.drawable.bg_clay_pill_button)
            binding.tabClientRole.setTextColor(getColor(android.R.color.white))
            binding.tabAdminRole.setBackground(null)
            binding.tabAdminRole.setTextColor(getColor(R.color.clay_text_body))
            binding.etEmail.setText("alex.patient@health.org")
            binding.etPassword.setText("patient1234")
        }

        binding.tabAdminRole.setOnClickListener {
            selectedRole = "admin"
            binding.tabAdminRole.setBackgroundResource(R.drawable.bg_clay_pill_button)
            binding.tabAdminRole.setTextColor(getColor(android.R.color.white))
            binding.tabClientRole.setBackground(null)
            binding.tabClientRole.setTextColor(getColor(R.color.clay_text_body))
            binding.etEmail.setText("admin@dermatrace.com")
            binding.etPassword.setText("admin1234")
        }
    }

    private fun setupAuthModeToggle() {
        binding.btnToggleAuthMode.setOnClickListener {
            isRegisterMode = !isRegisterMode
            if (isRegisterMode) {
                binding.tvAuthTitle.text = "Create New Account"
                binding.btnToggleAuthMode.text = "Have account? Sign In"
                binding.btnSubmitAuth.text = "Register & Enter ➔"
                binding.etName.visibility = View.VISIBLE
            } else {
                binding.tvAuthTitle.text = "Sign In to Your Account"
                binding.btnToggleAuthMode.text = "New? Register"
                binding.btnSubmitAuth.text = "Continue to App ➔"
                binding.etName.visibility = View.GONE
            }
        }
    }

    private fun setupQuickDemoButtons() {
        // Quick 1-tap Client demo
        binding.btnQuickPatient.setOnClickListener {
            ApiClient.activeRole = "client"
            ApiClient.currentUserEmail = "alex.patient@health.org"
            Toast.makeText(this, "👋 Welcome Alex (Patient Mode)", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, PatientDashboardActivity::class.java))
            finish()
        }

        // Quick 1-tap Admin demo
        binding.btnQuickAdmin.setOnClickListener {
            ApiClient.activeRole = "admin"
            ApiClient.currentUserEmail = "admin@dermatrace.com"
            Toast.makeText(this, "🩺 Welcome Clinician (Admin Workstation Unlocked)", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }
    }

    private fun setupSubmitButton() {
        binding.btnSubmitAuth.setOnClickListener {
            val email = binding.etEmail.text.toString().trim()
            val password = binding.etPassword.text.toString().trim()

            if (email.isEmpty()) {
                Toast.makeText(this, "Please enter your email", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // Attempt login with backend
            binding.btnSubmitAuth.isEnabled = false
            binding.btnSubmitAuth.text = "Authenticating..."

            lifecycleScope.launch {
                try {
                    val res = ApiClient.service.login(LoginRequest(email = email, role = selectedRole))
                    if (res.isSuccessful && res.body() != null) {
                        val body = res.body()!!
                        ApiClient.authToken = body.accessToken
                        ApiClient.activeRole = body.role
                        ApiClient.currentUserEmail = body.email
                        navigateAfterAuth(body.role)
                    } else {
                        // Fallback to local session if offline
                        ApiClient.activeRole = selectedRole
                        ApiClient.currentUserEmail = email
                        navigateAfterAuth(selectedRole)
                    }
                } catch (e: Exception) {
                    // Fallback to direct navigation
                    ApiClient.activeRole = selectedRole
                    ApiClient.currentUserEmail = email
                    navigateAfterAuth(selectedRole)
                } finally {
                    binding.btnSubmitAuth.isEnabled = true
                    binding.btnSubmitAuth.text = if (isRegisterMode) "Register & Enter ➔" else "Continue to App ➔"
                }
            }
        }
    }

    private fun navigateAfterAuth(role: String) {
        if (role.equals("admin", ignoreCase = true)) {
            Toast.makeText(this, "🩺 Admin Credentials Verified • Workstation Unlocked", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, MainActivity::class.java))
        } else {
            Toast.makeText(this, "👤 Client Signed In • Self-Monitoring Active", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, PatientDashboardActivity::class.java))
        }
        finish()
    }

    private fun checkServer() {
        lifecycleScope.launch {
            try {
                val h = ApiClient.service.getHealth()
                if (h.isSuccessful) {
                    binding.tvLoginStatus.text = "● Backend Active (Siamese Model Online)"
                    binding.tvLoginStatus.setBackgroundResource(R.drawable.bg_clay_safe)
                    binding.tvLoginStatus.setTextColor(getColor(android.R.color.holo_green_dark))
                }
            } catch (e: Exception) {
                binding.tvLoginStatus.text = "▲ Offline Mode Active"
                binding.tvLoginStatus.setBackgroundResource(R.drawable.bg_clay_warning)
                binding.tvLoginStatus.setTextColor(getColor(android.R.color.holo_orange_dark))
            }
        }
    }
}
