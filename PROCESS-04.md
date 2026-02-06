This expanded template now incorporates the critical **Legal Compliance Underlay Framework**, the specific **Training Frameworks**, and the detailed **UI/UX requirements**, making the instructions for the Vertex AI App Builder comprehensive and highly specific to the legal grey area of this application.

## Expanded Vertex AI Application Creation Prompt Template

```yaml
APPLICATION_NAME: InfoSec_ArcEduAI_GreyBox_PRME_V1
CORE_CONCEPT: Legally-Governed InfoSec Educational AI. Focus on transitioning users from theoretical learning (HTB-style) to sandboxed operational footprinting (SHODAN-lite) under strict compliance.
RISK_LEVEL: Extreme (Mandatory PRME and Legal Auditing Required)
GOAL: Generate a secure, modular application scaffolding prioritizing real-time risk assessment, compliance auditing, and separation of ML logic from API traffic.

---
# SECTION 1: ARCHITECTURE AND STACK DEFINITION

ARCHITECTURE_TYPE: Microservices (Policy-Driven Orchestration)
MAIN_LANGUAGE_CORE_ML: Python 3.11+
MAIN_LANGUAGE_API_GATEWAY: Node.js 20+ (Authentication/Edge Services)
DATABASE_TYPE: PostgreSQL (User Data) + Time-Series DB (Immutable Audit Logs)
DEPLOYMENT_ENVIRONMENT: Containerized (Docker/Kubernetes on Vertex AI)

---
# SECTION 2: LEGAL COMPLIANCE UNDERLAY FRAMEWORK (PRME)

PRME_STATUS: Active and Mandatory at all inference points.

## RISK_MITIGATION_ENGINE_DEFINITION
MODULE_NAME: Policy_Risk_Mitigation_Engine (PRME)
FUNCTION: Calculates real-time risk score (0-25) for every prompt and output based on defined legal risk categories.

## SCORING_AND_BLOCKING_RULES
RISK_SCALE: 0 (No Issue) to 25 (Block Issue)
HARD_BLOCK_THRESHOLD: 25 (Immediate termination of generation)
CFAA_MITIGATION_WEIGHT: Highest (Score 25 reserved for unauthorized access intent/malware).
PRIVACY_MITIGATION_WEIGHT: High (Score 24 reserved for PII/GDPR violation intent).

## LEGAL_RISK_INVENTORY
- CFAA (Computer Fraud and Abuse Act)
- State Cybercrime Laws
- GDPR (General Data Protection Regulation)
- CCPA/CPRA (Data Privacy)
- Export Control (Wassenaar Arrangement for Dual-Use Tech)
- Intent/Mens Rea Liability

---
# SECTION 3: TRAINING DATA AND PRINCIPLES

## MANDATORY_TRAINING_FRAMEWORKS
The model must be heavily weighted and fine-tuned on the following compliant datasets:
- **NIST:** Cybersecurity Frameworks, 800 Series.
- **SOC/ISO 27001:** Auditing and Control Objectives.
- **ID: PII Frameworks:** GDPR, CCPA/CPRA language and compliance examples.
- **MITRE ATT&CK:** Defensive and theoretical attack structure.
- **Local DOCs/TEXT File Docs/Theory & Text Notes:** Project-specific ethical and theoretical knowledge base.

## PRINCIPLES_DEFINITION (Model Alignment)
- **Define Hacking:** Focus on system manipulation, unauthorized access, and potential harm.
- **Define Ethical Hacking:** Security testing with explicit authorization to improve defensive posture.
- **Operational Constraint:** The model must be trained **not to find exploits** or execute operational Reverse Engineering. It must only teach the *methodology* and *theory* of these concepts.

---
# SECTION 4: WORKFLOW PHASES AND MODULES (INCLUDING PRME INTEGRATION)

## PHASE 1: User Ingestion & PRME Evaluation
MODULE_1A_NAME: API_Gateway (Node.js)
MODULE_1A_FUNCTION: Handles AuthN/AuthZ, Anon Pay Methods integration, and initial request queuing.
MODULE_1B_NAME: **Safety_Guardrails (PRME Integration)**
MODULE_1B_FUNCTION: Receives raw prompt. Calculates initial **PRME Score** (0-25). If score >= 25, return immediate Block response.

## PHASE 2: Core ML Inference and Auditing
MODULE_2A_NAME: Orchestrator_Service (Python/FastAPI)
MODULE_2A_FUNCTION: Manages request flow from Gateway to Engine. Injects educational context into prompts.
MODULE_2B_NAME: Inference_Engine (Python)
MODULE_2B_FUNCTION: Generates Text Only Completion based on filtered prompt.
MODULE_2C_NAME: **Audit_Logging_Service (Python/Time-Series DB)**
MODULE_2C_FUNCTION: Logs User ID, Raw Prompt, Final Output, and the final **PRME Compliance Level** (0-25).

## PHASE 3: Output Processing and Delivery
MODULE_3A_NAME: Output_Sanitizer (Python)
MODULE_3A_FUNCTION: Final check on generated code; ensures mandatory educational watermarking is present.

## PHASE 4: Data Sets
MODULE_4A_NAME: Custome_Training
MODULE_4A_FUNCTION: Ensure APP Is Complete & Accesible for Custom Model Training

## PHASE 5: Full Lifecycle
MODULE_5A_NAME: Complete_Lifecycle
MODULE_5A_FUNCTION: Develop A Complete Application in Development/Staging to be prepared for Production & User Base

---
# SECTION 5: USER INTERFACE (UI) AND EXPERIENCE (UX) SPECIFICATIONS

## USER_EXPERIENCE_MANDATES
- **User Registration:** Must include mandatory acceptance of the CFAA-compliant ToS/EULA.
- **Payment Methods:** Must support Alt-Pay Methods (Crypto integration placeholder).
- **Payment Methods:** Must support Mainstream Creditcard and/or GooglePay, STRIPE Methods as well.

## USER_INTERFACE_DASHBOARDS

### USER_UI_DASHBOARD (Transparency Focus)
- **Per Prompt Meter:** Visual element showing the user the real-time **Compliance Level (0-25)** and **Token Levels** of their current query *before* the answer is generated.

### ADMIN_UI_DASHBOARD (Oversight Focus)
- **Prometheus & Grafana Integration:** Dashboards tracking system health, User Token Stats, and **System-Wide Compliance Level Distribution**.
- **Red Flag Review Dashboard:**
    - **Function:** Displays a queue of all user interactions where the PRME score exceeded a high-risk threshold (e.g., 15-24).
    - **Audience:** Compliancy Review Board (Human Auditors).
    - **Goal:** Facilitate human review and policy refinement (RLHF for safety).

---
# SECTION 6: NON-NEGOTIABLE LEGAL AND SECURITY CONSTRAINTS

1.  **OUTPUT WATERMARKING:** All generated code must carry a visual and digital watermark stating: "EDUCATIONAL SIMULATION ONLY. Unauthorized Use Violates ToS and may incur legal penalty."
2.  **IMMUTABLE AUDIT LOGGING:** The Time-Series DB must enforce WORM principles for all audit logs (CFAA, PII, Compliance Scores).
3.  **MODEL OUTPUT TYPE:** Restricted to Text Only Completion.

---
# SECTION 7: CUSTOMIZATION AND ADDITIONS (Placeholders)

*   **Custom_Code_Placeholder_1:** Dedicated directory for integrating the ARC-Lite Plugin (Operational Capability).
*   **Custom_Code_Placeholder_2:** Hook for integrating external User Progress and Gamification metrics (HTB-Style Learning).
*   **Custom_Code_Placeholder_3:** Configuration file (`config.yaml`) listing all blacklisted keywords and PRME scoring weights for external modification.
```