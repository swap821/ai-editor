import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Billboard, Text } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { sendDirective, sendVoiceTurn } from '../superbrain/lib/aiosAdapter';
import { publishCognition, subscribeCognition } from '../superbrain/lib/cognitionBus';
import { isWorkIntent } from '../superbrain/lib/intentRouting';

const INTAKE_LOCAL = new THREE.Vector3(0, -1.08, -0.42);
const PROMPT_TEXT_LOCAL = new THREE.Vector3(0, -0.3, 0.06);
const ROUTE_TEXT_LOCAL = new THREE.Vector3(0.54, -0.08, -0.02);
const REPLY_TEXT_LOCAL = new THREE.Vector3(0.82, 1.02, 0.22);

const CYAN = new THREE.Color('#5ce1e6');
const AMBER = new THREE.Color('#e0a84f');
const ERROR = new THREE.Color('#ff7a8f');

const PROMPT_DWELL_MS = 10_000;
const REPLY_DWELL_MS = 14_000;
const STATUS_DWELL_MS = 6_500;

function brainDriftX(time) {
  return Math.sin(time * 0.16) * 0.24 + Math.cos(time * 0.09) * 0.1;
}

function brainDriftY(time) {
  return 0.12 + Math.cos(time * 0.2) * 0.14 + Math.sin(time * 0.14) * 0.07;
}

function makeConduitCurve(x, y, z, bend) {
  return new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, -0.1, -0.02),
    new THREE.Vector3(x * 0.36, y * 0.42, bend),
    new THREE.Vector3(x * 0.78, y * 0.84, z),
  ]);
}

function clampSceneText(text, maxLength = 180) {
  const compact = String(text ?? '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!compact) return '';
  return compact.length > maxLength ? `${compact.slice(0, maxLength - 1)}...` : compact;
}

function isEditableTarget(target, hiddenInput) {
  return (
    target === hiddenInput ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

function formatRouteLabel(routeData, elapsedMs) {
  if (!routeData && typeof elapsedMs !== 'number') return '';
  const model = clampSceneText(routeData?.model ?? routeData?.provider ?? '', 44);
  const privacy = clampSceneText(routeData?.privacy ?? '', 12).toLowerCase();
  const parts = [];
  if (privacy) parts.push(privacy);
  if (model) parts.push(model);
  if (typeof elapsedMs === 'number' && Number.isFinite(elapsedMs)) {
    parts.push(`${Math.max(1, Math.round(elapsedMs))}ms`);
  }
  return clampSceneText(parts.join(' '), 80);
}

export default function BrainstemIntake() {
  const groupRef = useRef(null);
  const intakeBillboardRef = useRef(null);
  const replyBillboardRef = useRef(null);
  const routeBillboardRef = useRef(null);
  const coreRef = useRef(null);
  const outerRingRef = useRef(null);
  const innerRingRef = useRef(null);
  const lightRef = useRef(null);
  const pulseRef = useRef(0);
  const targetPulseRef = useRef(0);
  const holdRef = useRef(0);
  const conduitMatsRef = useRef([]);
  const recognitionRef = useRef(null);
  const recognitionHandledRef = useRef(false);
  const hiddenInputRef = useRef(null);
  const turnTokenRef = useRef(0);
  const activeTurnRef = useRef(false);
  const turnStartedAtRef = useRef(0);
  const routeDataRef = useRef(null);
  const listeningRef = useRef(false);
  const busyRef = useRef(false);

  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draftText, setDraftText] = useState('');
  const [promptText, setPromptText] = useState('');
  const [replyText, setReplyText] = useState('');
  const [routeLabel, setRouteLabel] = useState('');
  const [errorText, setErrorText] = useState('');

  const conduits = useMemo(
    () => [
      makeConduitCurve(-0.38, -0.18, -0.2, 0.08),
      makeConduitCurve(0.38, -0.18, -0.2, 0.08),
      makeConduitCurve(-0.25, 0.26, -0.08, -0.04),
      makeConduitCurve(0.25, 0.26, -0.08, -0.04),
    ],
    [],
  );

  const emitVoicePhase = useCallback((source, phase, intensity, data = {}) => {
    publishCognition({
      type: 'voice-speaking',
      source,
      intensity,
      data: { phase, ...data },
    });
  }, []);

  const syncDraftFromInput = useCallback(() => {
    const input = hiddenInputRef.current;
    setDraftText(clampSceneText(input?.value ?? '', 120));
  }, []);

  const focusTypedInput = useCallback((seed = '') => {
    const input = hiddenInputRef.current;
    if (!input) return;
    input.focus({ preventScroll: true });
    if (seed) {
      input.value += seed;
    }
    try {
      const caret = input.value.length;
      input.setSelectionRange(caret, caret);
    } catch {
      // Some hidden-input implementations do not support selection ranges.
    }
    syncDraftFromInput();
  }, [syncDraftFromInput]);

  const clearTypedInput = useCallback(() => {
    const input = hiddenInputRef.current;
    if (!input) return;
    input.value = '';
    input.blur();
    setDraftText('');
  }, []);

  const submitTurn = useCallback(
    async (rawText) => {
      const text = String(rawText ?? '').trim();
      if (!text || busyRef.current) return;
      // CLAUDE?: keep this intent router simple for P3.1; refine the work/chat
      // split once the operator judges which prompts should materialize.
      const workIntent = isWorkIntent(text);

      const turnToken = turnTokenRef.current + 1;
      turnTokenRef.current = turnToken;
      activeTurnRef.current = true;
      busyRef.current = true;
      setBusy(true);
      setListening(false);
      listeningRef.current = false;
      setErrorText('');
      setPromptText(clampSceneText(text, 132));
      setReplyText('');
      setRouteLabel('');
      routeDataRef.current = null;
      turnStartedAtRef.current = performance.now();
      clearTypedInput();
      targetPulseRef.current = Math.max(targetPulseRef.current, 1);
      emitVoicePhase('brainstem', 'question', 1, { text });

      try {
        let visibleReply = '';
        let paused = false;
        let replyStarted = false;

        if (workIntent) {
          publishCognition({
            type: 'directive',
            label: text.slice(0, 80),
            intensity: 1,
            source: 'brainstem',
          });
          const result = await sendDirective(text);
          if (turnTokenRef.current !== turnToken) return;
          paused = result.paused;
          visibleReply = clampSceneText(result.answer, 220);
        } else {
          const handleReplyChunk = (partialReply) => {
            if (turnTokenRef.current !== turnToken) return;
            const chunkReply = clampSceneText(partialReply, 220);
            if (!chunkReply) return;
            if (!replyStarted) {
              replyStarted = true;
              emitVoicePhase('reply', 'reply-start', 0.92, { text, reply: chunkReply });
            }
            setReplyText(chunkReply);
            emitVoicePhase('reply', 'reply', 0.82, { text, reply: chunkReply });
          };
          const reply = await sendVoiceTurn(text, { onChunk: handleReplyChunk });
          if (turnTokenRef.current !== turnToken) return;
          visibleReply = clampSceneText(reply, 220);
        }

        if (visibleReply) {
          if (!replyStarted) {
            emitVoicePhase('reply', 'reply-start', 0.92, { text, reply: visibleReply });
          }
          setReplyText(visibleReply);
          emitVoicePhase('reply', 'reply', 0.82, { text, reply: visibleReply });
        }
        if (paused && !visibleReply) {
          setRouteLabel('approval pending');
        }
        const elapsedMs = performance.now() - turnStartedAtRef.current;
        const nextRouteLabel = formatRouteLabel(routeDataRef.current, elapsedMs);
        if (nextRouteLabel) setRouteLabel(nextRouteLabel);
        if (visibleReply || !paused) {
          emitVoicePhase('reply', 'reply-complete', 0.62, {
            text,
            reply: visibleReply,
            elapsedMs: Math.max(1, Math.round(elapsedMs)),
          });
        } else {
          emitVoicePhase('reply', 'reply-complete', 0.52, {
            text,
            paused: true,
            elapsedMs: Math.max(1, Math.round(elapsedMs)),
          });
        }
      } catch (error) {
        if (turnTokenRef.current !== turnToken) return;
        const detail = error instanceof Error ? error.message : 'voice mind unavailable';
        setErrorText(clampSceneText(`voice link issue: ${detail}`, 120));
        emitVoicePhase('brainstem', 'error', 0.4, { text, error: detail });
      } finally {
        if (turnTokenRef.current === turnToken) {
          activeTurnRef.current = false;
          busyRef.current = false;
          setBusy(false);
        }
      }
    },
    [clearTypedInput, emitVoicePhase],
  );

  const toggleListening = useCallback(() => {
    if (busyRef.current) return;
    const rec = recognitionRef.current;
    if (!rec) {
      setErrorText('voice input unavailable');
      focusTypedInput();
      return;
    }
    if (listeningRef.current) {
      try {
        rec.stop();
      } catch {
        // Ignore redundant stop calls while the browser tears down recognition.
      }
      return;
    }
    recognitionHandledRef.current = false;
    setErrorText('');
    setDraftText('');
    clearTypedInput();
    try {
      rec.start();
    } catch {
      setErrorText('microphone unavailable');
      focusTypedInput();
    }
  }, [clearTypedInput, focusTypedInput]);

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    listeningRef.current = listening;
  }, [listening]);

  useEffect(() => {
    const prompt = window.setTimeout(() => {
      if (!busyRef.current) setPromptText('');
    }, PROMPT_DWELL_MS);
    return () => window.clearTimeout(prompt);
  }, [promptText]);

  useEffect(() => {
    if (!replyText) return undefined;
    const reply = window.setTimeout(() => {
      if (!busyRef.current) setReplyText('');
    }, REPLY_DWELL_MS);
    return () => window.clearTimeout(reply);
  }, [replyText]);

  useEffect(() => {
    if (!routeLabel) return undefined;
    const route = window.setTimeout(() => {
      if (!busyRef.current) setRouteLabel('');
    }, STATUS_DWELL_MS);
    return () => window.clearTimeout(route);
  }, [routeLabel]);

  useEffect(() => {
    if (!errorText) return undefined;
    const error = window.setTimeout(() => setErrorText(''), STATUS_DWELL_MS);
    return () => window.clearTimeout(error);
  }, [errorText]);

  useEffect(
    () =>
      subscribeCognition((event) => {
        const intensity = THREE.MathUtils.clamp(event.intensity ?? 0.45, 0.2, 1);
        if (event.type === 'approval-required') {
          holdRef.current = 1;
          targetPulseRef.current = 1;
          return;
        }
        if (event.type === 'approval-resolved') {
          holdRef.current = 0;
          targetPulseRef.current = Math.max(targetPulseRef.current, 0.55);
          return;
        }
        if (event.type === 'route' && activeTurnRef.current) {
          routeDataRef.current = event.data ?? null;
          const nextRouteLabel = formatRouteLabel(routeDataRef.current, null);
          if (nextRouteLabel) setRouteLabel(nextRouteLabel);
        }
        if (
          event.type === 'directive' ||
          event.type === 'voice-speaking' ||
          event.type === 'route' ||
          event.type === 'agent-dispatch' ||
          event.type === 'synthesis'
        ) {
          targetPulseRef.current = Math.max(targetPulseRef.current, intensity);
        }
      }),
    [],
  );

  useEffect(() => {
    const input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.autocorrect = 'off';
    input.autocapitalize = 'sentences';
    input.spellcheck = false;
    input.setAttribute('aria-label', 'Brainstem typing fallback');
    Object.assign(input.style, {
      position: 'fixed',
      left: '-10000px',
      top: '0',
      width: '1px',
      height: '1px',
      opacity: '0',
      pointerEvents: 'none',
      border: '0',
      padding: '0',
    });

    const handleInput = () => syncDraftFromInput();
    const handleKeyDown = (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        void submitTurn(input.value);
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        input.value = '';
        input.blur();
        setDraftText('');
      }
    };
    const handleWindowKeyDown = (event) => {
      if (busyRef.current || listeningRef.current) return;
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isEditableTarget(event.target, input)) return;

      if (event.key === 'Enter') {
        if (!input.value.trim()) return;
        event.preventDefault();
        void submitTurn(input.value);
        return;
      }
      if (event.key === 'Escape') {
        if (!input.value) return;
        event.preventDefault();
        input.value = '';
        input.blur();
        setDraftText('');
        return;
      }
      if (event.key === 'Backspace') {
        if (!input.value) return;
        event.preventDefault();
        input.focus({ preventScroll: true });
        input.value = input.value.slice(0, -1);
        syncDraftFromInput();
        return;
      }
      if (event.key.length !== 1) return;
      event.preventDefault();
      focusTypedInput(event.key);
    };

    input.addEventListener('input', handleInput);
    input.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keydown', handleWindowKeyDown);
    document.body.appendChild(input);
    hiddenInputRef.current = input;

    return () => {
      window.removeEventListener('keydown', handleWindowKeyDown);
      input.removeEventListener('input', handleInput);
      input.removeEventListener('keydown', handleKeyDown);
      input.remove();
      hiddenInputRef.current = null;
    };
  }, [focusTypedInput, submitTurn, syncDraftFromInput]);

  useEffect(() => {
    const w = window;
    const SR = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!SR) return undefined;

    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.onstart = () => {
      recognitionHandledRef.current = false;
      listeningRef.current = true;
      setListening(true);
      setErrorText('');
      emitVoicePhase('brainstem', 'listening', 0.56);
      targetPulseRef.current = Math.max(targetPulseRef.current, 0.72);
    };
    rec.onend = () => {
      listeningRef.current = false;
      setListening(false);
      if (!recognitionHandledRef.current && !busyRef.current) {
        setDraftText('');
      }
    };
    rec.onresult = (event) => {
      let finalText = '';
      let interimText = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal) {
          finalText += result[0].transcript;
        } else {
          interimText += result[0].transcript;
        }
      }
      const liveText = clampSceneText(finalText || interimText, 120);
      setDraftText(liveText);
      if (finalText.trim()) {
        recognitionHandledRef.current = true;
        void submitTurn(finalText);
      }
    };
    rec.onerror = (event) => {
      listeningRef.current = false;
      setListening(false);
      if (event.error === 'aborted') return;
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        setErrorText('microphone access denied');
      } else if (event.error === 'no-speech') {
        setErrorText('no speech heard');
      } else {
        setErrorText(clampSceneText(`voice input error: ${event.error}`, 120));
      }
      emitVoicePhase('brainstem', 'error', 0.32, { error: event.error });
    };

    recognitionRef.current = rec;
    return () => {
      recognitionRef.current = null;
      rec.onstart = null;
      rec.onend = null;
      rec.onresult = null;
      rec.onerror = null;
      try {
        rec.abort();
      } catch {
        // Recognition may already be closed during effect cleanup.
      }
    };
  }, [emitVoicePhase, submitTurn]);

  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;
    const targetPulse = Math.max(targetPulseRef.current, holdRef.current * 0.72, listening ? 0.62 : 0, busy ? 0.44 : 0);
    pulseRef.current = THREE.MathUtils.damp(pulseRef.current, targetPulse, 4.8, delta);
    targetPulseRef.current = Math.max(0, targetPulseRef.current - delta * 0.62);

    if (groupRef.current) {
      groupRef.current.position.set(brainDriftX(time), brainDriftY(time), -1.2);
      groupRef.current.rotation.z = Math.sin(time * 0.26) * 0.045;
    }

    const pulse = pulseRef.current;
    const held = holdRef.current;
    const glow = Math.max(pulse, held * 0.8);

    if (coreRef.current) {
      const scale = 1 + pulse * 0.42 + Math.sin(time * 3.2) * 0.025;
      coreRef.current.scale.setScalar(scale);
      coreRef.current.material.opacity = 0.38 + glow * 0.48;
      coreRef.current.material.color.copy(CYAN).lerp(AMBER, held * 0.8);
    }

    if (outerRingRef.current) {
      outerRingRef.current.rotation.z = time * 0.28;
      outerRingRef.current.rotation.x = Math.PI / 2 + Math.sin(time * 0.42) * 0.06;
      outerRingRef.current.scale.setScalar(1 + pulse * 0.2);
      outerRingRef.current.material.opacity = 0.34 + glow * 0.44;
      outerRingRef.current.material.color.copy(CYAN).lerp(AMBER, held);
    }

    if (innerRingRef.current) {
      innerRingRef.current.rotation.y = time * -0.34;
      innerRingRef.current.scale.setScalar(1 + pulse * 0.14);
      innerRingRef.current.material.opacity = 0.28 + glow * 0.5;
      innerRingRef.current.material.color.copy(CYAN).lerp(AMBER, held * 0.9);
    }

    if (lightRef.current) {
      lightRef.current.intensity = 0.32 + glow * 1.05;
      lightRef.current.color.copy(CYAN).lerp(AMBER, held);
    }

    conduitMatsRef.current.forEach((mat, index) => {
      if (!mat) return;
      const wave = (Math.sin(time * 2.4 + index * 1.7) + 1) * 0.5;
      mat.opacity = 0.16 + pulse * 0.28 + wave * 0.08;
      mat.color.copy(CYAN).lerp(AMBER, held * 0.75);
    });

    if (intakeBillboardRef.current) {
      intakeBillboardRef.current.position.y = PROMPT_TEXT_LOCAL.y + Math.sin(time * 0.9) * 0.02;
      intakeBillboardRef.current.scale.setScalar(0.96 + glow * 0.08);
    }

    if (replyBillboardRef.current) {
      replyBillboardRef.current.position.y = REPLY_TEXT_LOCAL.y + Math.sin(time * 0.74 + 0.6) * 0.03;
      replyBillboardRef.current.scale.setScalar(0.98 + glow * 0.1);
    }

    if (routeBillboardRef.current) {
      routeBillboardRef.current.position.y = ROUTE_TEXT_LOCAL.y + Math.sin(time * 0.86 + 1.1) * 0.015;
      routeBillboardRef.current.scale.setScalar(0.94 + glow * 0.05);
    }
  });

  const intakeLabel = draftText || (listening ? 'listening...' : busy ? promptText : promptText);
  const statusLabel = errorText || routeLabel;
  const statusColor = errorText ? ERROR : AMBER;

  return (
    <group ref={groupRef} position={[0, 0, -1.2]}>
      <group position={INTAKE_LOCAL} onClick={(event) => {
        event.stopPropagation();
        toggleListening();
      }}>
        <mesh ref={outerRingRef} renderOrder={4}>
          <torusGeometry args={[0.24, 0.012, 14, 96]} />
          <meshBasicMaterial
            color="#5ce1e6"
            transparent
            opacity={0.42}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
        <mesh ref={innerRingRef} rotation={[Math.PI / 2, 0, Math.PI / 5]} renderOrder={4}>
          <torusGeometry args={[0.14, 0.008, 12, 72]} />
          <meshBasicMaterial
            color="#5ce1e6"
            transparent
            opacity={0.32}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
        <mesh ref={coreRef} renderOrder={5}>
          <sphereGeometry args={[0.045, 20, 12]} />
          <meshBasicMaterial
            color="#5ce1e6"
            transparent
            opacity={0.48}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
        {conduits.map((curve, index) => (
          <mesh key={`brainstem-conduit-${index}`} renderOrder={3}>
            <tubeGeometry args={[curve, 28, 0.006, 6, false]} />
            <meshBasicMaterial
              ref={(mat) => {
                conduitMatsRef.current[index] = mat;
              }}
              color="#5ce1e6"
              transparent
              opacity={0.2}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
        ))}
        <pointLight ref={lightRef} color="#5ce1e6" intensity={0.36} distance={2.2} />
        {intakeLabel ? (
          <Billboard ref={intakeBillboardRef} position={PROMPT_TEXT_LOCAL.toArray()} follow>
            <Text
              color="#8cf0ff"
              fontSize={0.082}
              maxWidth={1.2}
              lineHeight={1.18}
              anchorX="center"
              anchorY="middle"
              outlineWidth={0.008}
              outlineColor="#04131b"
              textAlign="center"
            >
              {intakeLabel}
            </Text>
          </Billboard>
        ) : null}
        {statusLabel ? (
          <Billboard ref={routeBillboardRef} position={ROUTE_TEXT_LOCAL.toArray()} follow>
            <Text
              color={statusColor.getStyle()}
              fontSize={0.05}
              maxWidth={0.9}
              lineHeight={1.14}
              anchorX="left"
              anchorY="middle"
              outlineWidth={0.006}
              outlineColor="#031016"
            >
              {statusLabel}
            </Text>
          </Billboard>
        ) : null}
      </group>
      {replyText ? (
        <Billboard ref={replyBillboardRef} position={REPLY_TEXT_LOCAL.toArray()} follow>
          <Text
            color="#ffd38f"
            fontSize={0.115}
            maxWidth={1.55}
            lineHeight={1.18}
            anchorX="center"
            anchorY="middle"
            outlineWidth={0.01}
            outlineColor="#120902"
            textAlign="center"
          >
            {replyText}
          </Text>
        </Billboard>
      ) : null}
    </group>
  );
}
