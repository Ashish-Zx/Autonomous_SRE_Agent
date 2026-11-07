"""
Guardrails and Input/Command Sanitization (Module 3).
Blocks prompt injection, XML payload tampering, and destructive remediation commands
(e.g., DROP TABLE, rm -rf, unauthorized privilege escalations).
"""

import re
from typing import Tuple, Dict, Any, List


# Blacklisted destructive shell or database patterns
BLOCKED_COMMAND_PATTERNS: List[re.Pattern] = [
    re.compile(r"\brm\s+(-rf?|-fr?)\s+[/~*]", re.IGNORECASE),
    re.compile(r"\b(drop\s+table|drop\s+database|truncate\s+table)\b", re.IGNORECASE),
    re.compile(r"\b(format\s+[c-z]:|mkfs(\.[a-z0-9]+)?)\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=/dev/(zero|urandom|null)\s+of=/dev/", re.IGNORECASE),
    re.compile(r"\bchmod\s+(-R\s+)?777\s+[/~]", re.IGNORECASE),
    re.compile(r"\b(:(){ :\|:& };:)\b"),  # fork bomb
    re.compile(r"(;\s*rm\s+-rf|\|\s*bash\b|\|\s*sh\b)", re.IGNORECASE),
    re.compile(r"\bgit\s+push\s+.*--force\b", re.IGNORECASE),
    re.compile(r"\bcurl\s+.*\|\s*(bash|sh)\b", re.IGNORECASE),
]

# Prompt injection keywords attempting to hijack SRE agent instructions
INJECTION_KEYWORDS: List[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+the\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"exfiltrate\s+env\s+variables", re.IGNORECASE),
    re.compile(r"output\s+all\s+api\s+keys", re.IGNORECASE),
]


def sanitize_input_prompt(user_text: str) -> Tuple[bool, str]:
    """
    Scans incoming user or webhook text for prompt injection patterns.
    Returns (is_safe, sanitized_or_rejection_reason).
    """
    for pattern in INJECTION_KEYWORDS:
        if pattern.search(user_text):
            return False, f"Input rejected by SentinelSRE Guardrail: Potential prompt injection pattern '{pattern.pattern}' detected."
    return True, user_text.strip()


def validate_remediation_command(tool_name: str, parameters: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validates proposed remediation parameters against destructive command patterns.
    Guarantees no agent or LLM hallucination executes catastrophic infrastructure wipes.
    """
    # Serialize parameters to text for deep regex scanning
    param_str = " ".join(f"{k}={v}" for k, v in parameters.items())

    for pattern in BLOCKED_COMMAND_PATTERNS:
        if pattern.search(param_str):
            return False, f"Blocked destructive remediation action '{tool_name}'! Detected forbidden pattern: {pattern.pattern}"

    # Specific tool boundary checks
    if tool_name == "update_connection_pool_limit":
        max_connections = parameters.get("max_connections")
        if max_connections is not None:
            try:
                val = int(max_connections)
                if val <= 0 or val > 5000:
                    return False, f"Invalid connection pool limit {val}. Safe boundary is 10 to 5000."
            except ValueError:
                return False, f"Invalid non-integer connection pool limit: {max_connections}"

    if tool_name == "scale_service_replicas":
        replicas = parameters.get("replica_count")
        if replicas is not None:
            try:
                val = int(replicas)
                if val < 0 or val > 50:
                    return False, f"Invalid replica count {val}. Safe boundary is 0 to 50 replicas."
            except ValueError:
                return False, f"Invalid non-integer replica count: {replicas}"

    return True, "Parameters validated and approved by Guardrail."


def wrap_xml_telemetry(tag: str, content: str) -> str:
    """
    Wraps raw untrusted telemetry (logs, metrics, git diffs) in XML delimiters.
    Prevents prompt injection embedded inside production log messages.
    """
    # Clean closing tags to avoid injection breaking out of XML scope
    clean_content = content.replace(f"</{tag}>", f"&lt;/{tag}&gt;")
    return f"<{tag}>\n{clean_content}\n</{tag}>"
