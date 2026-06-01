// rollbackEngine.js
import fs from 'fs';
import { execSync } from 'child_process';

/**
 * Ensures the workspace is a Git repository and takes a snapshot.
 */
export function createPreActionSnapshot(message = "Autonomous AI Pre-Action Snapshot") {
    try {
        // --- FIX: Create a .gitignore to protect locked database files ---
        if (!fs.existsSync('.gitignore')) {
            fs.writeFileSync('.gitignore', '*.sqlite\n*.sqlite-wal\n*.sqlite-shm\nnode_modules/\n.env\n');
        }

        // Initialize git if it doesn't exist
        if (!fs.existsSync('.git')) {
            execSync('git init');
            execSync('git add .');
            execSync('git commit -m "Initial system commit"');
        }
        
        // Stage all current changes and commit them as a snapshot
        execSync('git add .');
        
        try {
            execSync(`git commit -m "[SNAPSHOT] ${message}"`);
        } catch (commitError) {
            return "Workspace is already clean. No snapshot needed.";
        }
        
        return "Snapshot created successfully. Safe to proceed with actions.";
    } catch (e) {
        return `Snapshot creation failed: ${e.message}`;
    }
}

/**
 * Reverts the entire workspace back to the last snapshot.
 */
export function rollbackToLastSnapshot() {
    try {
        // Hard reset to the previous commit
        execSync('git reset --hard HEAD');
        // --- FIX: Explicitly exclude locked SQLite files from the clean wipe ---
        execSync('git clean -fd -e *.sqlite -e *.sqlite-wal -e *.sqlite-shm'); 
        return "CRITICAL RECOVERY SUCCESSFUL: Workspace rolled back to previous safe state.";
    } catch (e) {
        return `CRITICAL FAILURE: Rollback failed: ${e.message}`;
    }
}