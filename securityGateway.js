// securityGateway.js

// 1. High-Risk Command Blocklist (Scope Locking)
// 1. High-Risk Command Blocklist (Upgraded)
const DANGEROUS_COMMANDS = [
    'rm -rf', 'rm ', 'del /s', 'del *', 'format ', 'mkfs', 'dd ', 
    '> /dev/sda', 'chmod 777', 'chown', 'wget ', 'curl ',
    'invoke-webrequest', 'remove-item' // Block the root command entirely
];

// 2. Secret Scanning (Regex for common API keys and tokens)
const SECRET_PATTERNS = [
    /sk-[a-zA-Z0-9]{48}/, // Standard OpenAI/Anthropic Keys
    /(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}/, // AWS Access Keys
    /ghp_[a-zA-Z0-9]{36}/ // GitHub Personal Access Tokens
];

/**
 * Validates an AI intent against the deterministic security rules.
 * @param {string} command - The terminal command the AI wants to run.
 * @returns {object} { status: 'ALLOW' | 'BLOCK' | 'REQUIRE_HUMAN', reason: string }
 */
export function validateCommand(command) {
    if (!command) return { status: 'BLOCK', reason: 'Empty command.' };

    const cmdLower = command.toLowerCase();

    // Check 1: Secret Scanning
    for (const pattern of SECRET_PATTERNS) {
        if (pattern.test(command)) {
            return { 
                status: 'BLOCK', 
                reason: '[SECURITY ALERT] Hardcoded secret or API key detected in payload. Execution blocked.' 
            };
        }
    }

    // Check 2: Destructive Command Blocklist
    for (const blocked of DANGEROUS_COMMANDS) {
        if (cmdLower.includes(blocked.toLowerCase())) {
            return { 
                status: 'BLOCK', 
                reason: `[SECURITY ALERT] Command contains blocked dangerous syntax: '${blocked}'. Execution blocked.` 
            };
        }
    }

    // Check 3: Human-in-the-Loop Threshold
    // If the AI tries to install new software or modify network settings, it requires human approval.
    if (cmdLower.includes('pip install') || cmdLower.includes('npm install') || cmdLower.includes('git clone')) {
        return {
            status: 'REQUIRE_HUMAN',
            reason: '[AUTHORIZATION REQUIRED] Modifying system packages requires explicit human approval.'
        };
    }

    // If it passes all checks, fail-closed defaults to open only here
    return { status: 'ALLOW', reason: 'Command passed security gateway.' };
}