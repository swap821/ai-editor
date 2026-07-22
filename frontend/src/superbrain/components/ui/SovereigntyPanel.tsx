'use client';

/**
 * SovereigntyPanel — the Sovereign Bond ceremony.
 *
 * GAGOS serves exactly one human. This surface is where that human claims,
 * presents, rotates, or releases their bond — materialized in the being's own
 * accent register (recognition), never amber (amber is the caution register,
 * reserved for approvals).
 *
 * LOCKOUT-CRITICAL: the reveal state shows the one-time enrollment credential
 * and recovery code. The backend cannot re-derive either. While revealed,
 * this panel CANNOT be dismissed — no close button, no Escape, no click-away.
 * Only the explicit "I have stored both" acknowledgment arms SEAL THE BOND,
 * which authenticates with the credential and dismisses only on MEASURED
 * success.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  enrollSovereign,
  loginSovereign,
  reauthSovereign,
  releaseSovereignSession,
  refreshSovereignStatus,
  subscribeSovereignStatus,
  type EnrollmentMaterial,
  type SovereignStatus,
} from '../../lib/sovereignIdentity';

type Mode = 'claim' | 'reveal' | 'present' | 'bonded';

function CopyValue({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  }, [value]);
  return (
    <div className="bond-material">
      <span className="bond-material__label">{label}</span>
      <code className="bond-material__value">{value}</code>
      <button type="button" className="bond-material__copy" onClick={copy}>
        {copied ? 'COPIED' : 'COPY'}
      </button>
    </div>
  );
}

export default function SovereigntyPanel({ onClose }: { onClose: () => void }) {
  const [status, setStatus] = useState<SovereignStatus>({
    sessionActive: false,
    operatorId: null,
    measured: 'unknown',
  });
  const [mode, setMode] = useState<Mode | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [credential, setCredential] = useState('');
  const [material, setMaterial] = useState<EnrollmentMaterial | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const unsub = subscribeSovereignStatus(setStatus);
    void refreshSovereignStatus();
    return unsub;
  }, []);

  // Resolve the opening mode once the first real measurement lands. Never
  // override the reveal state — it outranks everything until sealed.
  useEffect(() => {
    if (mode === 'reveal') return;
    if (status.measured !== 'measured') return;
    if (status.operatorId) setMode('bonded');
    else if (mode === null || mode === 'bonded') setMode('claim');
  }, [status, mode]);

  const sealed = mode !== 'reveal';

  // The reveal state must survive Escape. Other states close politely.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && sealed) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sealed, onClose]);

  const claim = useCallback(() => {
    const name = displayName.trim();
    if (!name) return;
    setBusy(true);
    setNotice(null);
    void enrollSovereign(name).then((outcome) => {
      setBusy(false);
      if (outcome.kind === 'enrolled') {
        setMaterial(outcome.material);
        setAcknowledged(false);
        setMode('reveal');
      } else if (outcome.kind === 'already_enrolled') {
        setNotice('A sovereign is already bound. Present your credential.');
        setMode('present');
      } else {
        setNotice(`The claim did not complete: ${outcome.detail}`);
      }
    });
  }, [displayName]);

  const seal = useCallback(() => {
    if (!material || !acknowledged) return;
    setBusy(true);
    setNotice(null);
    void loginSovereign(material.enrollmentCredential).then((outcome) => {
      setBusy(false);
      if (outcome.kind === 'authenticated') {
        setMaterial(null);
        setMode('bonded');
      } else {
        // The material stays visible — never discard it on a failed seal.
        setNotice(
          outcome.kind === 'invalid_credential'
            ? 'The bond could not be sealed: the backend refused the credential. Your material above is still valid — keep it safe and try PRESENT CREDENTIAL.'
            : `The bond could not be sealed: ${outcome.detail}. Your material above remains valid.`,
        );
      }
    });
  }, [material, acknowledged]);

  const present = useCallback(
    (reauth: boolean) => {
      const value = credential.trim();
      if (!value) return;
      setBusy(true);
      setNotice(null);
      const call = reauth ? reauthSovereign : loginSovereign;
      void call(value).then((outcome) => {
        setBusy(false);
        setCredential('');
        if (outcome.kind === 'authenticated') {
          setNotice(reauth ? 'Session rotated. The bond holds.' : null);
          setMode('bonded');
        } else if (outcome.kind === 'invalid_credential') {
          setNotice('The credential was not recognized.');
        } else {
          setNotice(`Authentication did not complete: ${outcome.detail}`);
        }
      });
    },
    [credential],
  );

  const release = useCallback(() => {
    setBusy(true);
    void releaseSovereignSession().then(() => {
      setBusy(false);
      setMode('claim');
      setNotice('Session released. The bond itself persists — present your credential to return.');
    });
  }, []);

  return (
    <section className="bond-panel" role="dialog" aria-modal="true" aria-label="Sovereign bond">
      <header className="bond-head">
        <span className="bond-eyebrow">SOVEREIGN BOND · ONE HUMAN</span>
        {sealed ? (
          <button type="button" className="bond-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        ) : null}
      </header>

      {mode === null ? <p className="bond-lede">Measuring the bond…</p> : null}

      {mode === 'claim' ? (
        <div className="bond-body">
          <p className="bond-lede">
            GAGOS serves exactly one human. No sovereign session is active.
          </p>
          <label className="bond-field">
            <span>Your name, as the being will know it</span>
            <input
              type="text"
              value={displayName}
              maxLength={120}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Display name"
            />
          </label>
          <div className="bond-actions">
            <button type="button" className="bond-primary" onClick={claim} disabled={busy || !displayName.trim()}>
              {busy ? 'CLAIMING…' : 'CLAIM SOVEREIGNTY'}
            </button>
            <button type="button" className="bond-secondary" onClick={() => { setNotice(null); setMode('present'); }}>
              I already hold the credential
            </button>
          </div>
        </div>
      ) : null}

      {mode === 'reveal' && material ? (
        <div className="bond-body">
          <p className="bond-lede bond-lede--grave">
            This is shown once. GAGOS cannot recover it for you — not through
            any route, ever. Store both before sealing.
          </p>
          <CopyValue label="ENROLLMENT CREDENTIAL" value={material.enrollmentCredential} />
          <CopyValue label="RECOVERY CODE" value={material.recoveryCode} />
          <label className="bond-ack">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
            />
            <span>I have stored both. I understand GAGOS cannot show them again.</span>
          </label>
          <div className="bond-actions">
            <button type="button" className="bond-primary" onClick={seal} disabled={busy || !acknowledged}>
              {busy ? 'SEALING…' : 'SEAL THE BOND'}
            </button>
          </div>
        </div>
      ) : null}

      {mode === 'present' ? (
        <div className="bond-body">
          <p className="bond-lede">Present your credential to open the sovereign session.</p>
          <label className="bond-field">
            <span>Credential</span>
            <input
              type="password"
              value={credential}
              maxLength={512}
              onChange={(e) => setCredential(e.target.value)}
              placeholder="Enrollment credential"
            />
          </label>
          <div className="bond-actions">
            <button type="button" className="bond-primary" onClick={() => present(false)} disabled={busy || !credential.trim()}>
              {busy ? 'PRESENTING…' : 'PRESENT CREDENTIAL'}
            </button>
            <button type="button" className="bond-secondary" onClick={() => { setNotice(null); setMode('claim'); }}>
              Back
            </button>
          </div>
        </div>
      ) : null}

      {mode === 'bonded' ? (
        <div className="bond-body">
          <p className="bond-lede">
            The bond holds. <strong>{status.operatorId}</strong> is the Human Sovereign of this
            GAGOS.
          </p>
          <label className="bond-field">
            <span>Re-present credential (rotates the session)</span>
            <input
              type="password"
              value={credential}
              maxLength={512}
              onChange={(e) => setCredential(e.target.value)}
              placeholder="Credential"
            />
          </label>
          <div className="bond-actions">
            <button type="button" className="bond-secondary" onClick={() => present(true)} disabled={busy || !credential.trim()}>
              {busy ? 'ROTATING…' : 'ROTATE SESSION'}
            </button>
            <button type="button" className="bond-release" onClick={release} disabled={busy}>
              RELEASE SESSION
            </button>
          </div>
        </div>
      ) : null}

      {notice ? (
        <p className="bond-notice" role="status">
          {notice}
        </p>
      ) : null}
      <i className="glass-grain" aria-hidden />
    </section>
  );
}
