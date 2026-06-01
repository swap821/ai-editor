// secretScanner.js
import crypto from 'crypto';

export function scanAndRedactSecrets(payload) {
  if (!payload) return { scrubbedPayload: payload, secretsDetected: false };

  let scrubbedPayload = payload;
  let secretsDetected = false;

  // Industry-standard regex patterns for high-risk credentials
  const secretPatterns = [
    { 
      name: 'AWS_ACCESS_KEY', 
      regex: /(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}/g 
    },
    { 
      name: 'GITHUB_TOKEN', 
      regex: /(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}/g 
    },
    { 
      name: 'GENERIC_BEARER_TOKEN', 
      // Catches generic tokens assigned to variables (e.g., Bearer eyJhbGci...)
      regex: /Bearer\s+([a-zA-Z0-9\-\._~+\/]+=*)/g 
    },
    { 
      name: 'HARDCODED_PASSWORD', 
      // Catches password=... or secret=... assignments with high entropy
      regex: /(?:password|secret|api_key|apikey)\s*(?:=|:)\s*["']?([a-zA-Z0-9\-_]{12,})["']?/gi 
    }
  ];

  secretPatterns.forEach(pattern => {
    scrubbedPayload = scrubbedPayload.replace(pattern.regex, (match) => {
      secretsDetected = true;
      // Generate a short hash of the secret for the audit log, without exposing the secret itself
      const hash = crypto.createHash('sha256').update(match).digest('hex').substring(0, 8);
      return `<REDACTED: ${pattern.name}: ${hash}>`;
    });
  });

  return { scrubbedPayload, secretsDetected };
}