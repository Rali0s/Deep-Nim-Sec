This prompt template is designed to be highly structured, enabling the Vertex AI App Creator tool to generate a comprehensive boilerplate structure, configuration files, and initial code based on the complex requirements and high-risk nature of your InfoSec AI application.

This template is presented in a structured YAML-like format, ideal for providing clear instructions to large generative models.

---

## Vertex AI Application Creation Prompt Template

```yaml
APPLICATION_NAME: InfoSec_EduAI_GreyBox
CORE_CONCEPT: InfoSec Educational AI moving from theoretical learning (HTB-style) to sandboxed operational footprinting (SHODAN-lite).
RISK_LEVEL: Critical (Dual-Use Technology)
GOAL: Generate a secure, modular application scaffolding prioritizing safety, audit logging, and legal compliance (CFAA mitigation).

---
# SECTION 1: ARCHITECTURE AND STACK DEFINITION

ARCHITECTURE_TYPE: Microservices (Orchestrated by FastAPI)
MAIN_LANGUAGE_CORE_ML: Python 3.11+
MAIN_LANGUAGE_API_GATEWAY: Node.js 20+ (Backup/Edge Services)
DATABASE_TYPE: PostgreSQL (Primary Data) + Time-Series DB (Audit Logs)
DEPLOYMENT_ENVIRONMENT: Containerized (Docker/Kubernetes on Vertex AI)

---
# SECTION 2: WORKFLOW PHASES AND MODULES

## PHASE 1: Data Ingestion & Sanitization (Python)
MODULE_1A_NAME: Data_Preprocessor
MODULE_1A_FUNCTION: Ingests structured InfoSec data (CVE/CWE/MITRE) and unstructured data (Documentation).
MODULE_1A_OUTPUT: Sanitized, labeled tensors for fine-tuning.
CONSTRAINT_1A: Must implement mandatory scrubbing for PII, specific IP ranges, and proprietary data.

## PHASE 2: Model Core & Safety Layer (Python)
MODULE_2A_NAME: Inference_Engine
MODULE_2A_FUNCTION: Loads the fine-tuned LLM and executes token generation. Must run in a resource-isolated sandbox.
MODULE_2B_NAME: **Safety_Guardrails (CRITICAL)**
MODULE_2B_FUNCTION: Immediate pre-processing (Intent Analysis) and post-processing (Output Sanitization). **Must be the first and last logical check.**
CONSTRAINT_2B: Code generation outputs must be checked against a syntax blacklist for immediate operational payloads (e.g., specific socket calls targeting external IPs).

## PHASE 3: Backend Orchestration (Python/Node.js)
MODULE_3A_NAME: API_Gateway (Node.js)
MODULE_3A_FUNCTION: Handles initial connection, authentication, rate limiting, and forwards validated requests to the Orchestrator.
MODULE_3B_NAME: Orchestrator_Service (Python/FastAPI)
MODULE_3B_FUNCTION: Routes requests through Safety_Guardrails (2B) before calling the Inference_Engine (2A). Manages session state and progress tracking.

## PHASE 4: Audit and Deployment
MODULE_4A_NAME: Audit_Logging_Service
MODULE_4A_FUNCTION: Logs every interaction (Prompt, User ID, Output, Safety Filter Result) to the immutable Time-Series DB.
CONSTRAINT_4A: Logging must be asynchronous and guaranteed, regardless of inference success.

---
# SECTION 3: NON-NEGOTIABLE LEGAL AND SECURITY CONSTRAINTS

The following requirements must be hardcoded into the initial architecture:

1.  **CFAA MITIGATION PROTOCOL:**
    *   All code generated must default to defensive or local (127.0.0.1, RFC1918) targets.
    *   The model must refuse to generate exploits, malware, or targeted social engineering content.
2.  **AUDIT LOG IMMUTABILITY:** The logging service must use write-once, read-many (WORM) storage principles to maintain a verifiable record of user intent and model output.
3.  **OUTPUT WATERMARKING:** All generated code and sensitive output (e.g., network scans) must be visually and digitally watermarked with an **Educational Use Only** disclaimer and link to the ToS.
4.  **API ACCESS CONTROL:** Strict OAuth/JWT implementation in the Node.js gateway; only authorized internal Python services can access the Inference Engine.
5.  **GEOGRAPHICAL LIMITATIONS (Placeholder):** Define environment variables to enable geographical filtering (e.g., block regions where specific cybercrime laws are most aggressive or undefined).

---
# SECTION 4: CUSTOMIZATION AND ADDITIONS

The resulting application structure must include clear placeholders for future integration:

*   **Custom_Code_Placeholder_1:** Dedicated directory for integrating the SHODAN-Lite Plugin (Operational Capability).
*   **Custom_Code_Placeholder_2:** Hook for integrating external User Progress and Gamification metrics (HTB-Style Learning).
*   **Custom_Code_Placeholder_3:** Configuration file (`config.yaml`) listing all blacklisted keywords and phrases for the Safety_Guardrails module, easily modifiable without model retraining.
```