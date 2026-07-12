import { subscribeCognition } from '@/lib/cognitionBus';
'use client';

import { useEffect, useRef } from 'react';
import { Float, PerspectiveCamera, OrbitControls } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { preloadBrainScene } from '@/lib/brainScene';

import AccretionCore from './AccretionCore';
import CognitiveGrasp from '../components/canvas/CognitiveGrasp';
import PostFX from '../components/canvas/PostFX';
import NervousSystem from '../components/canvas/NervousSystem';
import CosmicBackground from '../components/canvas/CosmicBackground';
import CommandNerve3D from '../components/canvas/CommandNerve3D';
import KnowledgeHorizon from '../components/canvas/KnowledgeHorizon';
import MemoryGalaxy from '../components/canvas/MemoryGalaxy';
import BodySpeech from '../components/canvas/BodySpeech';
import { SubsystemErrorBoundary } from '../components/canvas/SubsystemErrorBoundary';


import { createSeededRandom } from '@/lib/seededRandom';
import { subscribeLifecycle, LifecycleState, ArrivalMode } from '@/lib/lifecycleStateMachine';
import { coalescenceEnvelope, ignitionPulse, awakenNotice } from '@/lib/openingMotion';
import { useReducedMotion } from '@/lib/reducedMotion';
import { getTurnMetabolismSnapshot, subscribeTurnMetabolism } from '@/lib/turnMetabolism';
import { deriveBodyPosture, postureColor01, POSTURE_DIAL } from '@/lib/bodyPosture';
import { getOrganismPhase } from '@/lib/organismPhaseBus';
import { getEffectiveOrganismPhase } from '@/lib/conversationPhaseBus';
import { FeatureGate } from './Performance/FeatureGate';

import {
  SuperbrainSceneProps,
  BurstState,
  CameraPushState,
  IdleControllerState,
  SCENE_UNIFORMS,
  BrainModel,
  PointerBrainClone,
  CameraDrift,
  OrganismFraming,
  WAVE_REGION_ANCHORS,
  waveOriginForLabel,
  waveLabelForTool,
  randomWaveOrigin,
  BEING_MODE,
  VOYAGE_SPEED,
  SHOW_MEMORY_GALAXY,
  HOLD_TINT,
  MODE_EMISSIVE,
  POSTURE_SCRATCH
} from '../components/canvas/SuperbrainScene.LEGACY';


const TAU = Math.PI * 2;
const IDLE_DELAY_S = 30;
const IDLE_EASE_IN_S = 2.5;
const IDLE_EASE_OUT_S = 0.6;
const IDLE_YAW_RATE = 0.02;

function isTextEntryFocused(): boolean {
  const active = document.activeElement;
  return (
    active instanceof HTMLInputElement ||
    active instanceof HTMLTextAreaElement ||
    active instanceof HTMLSelectElement ||
    (active instanceof HTMLElement && active.isContentEditable)
  );
}


export default function CortexEngine({ mode, activity, tier = 'high', sky = 'voyage', surface = 'web' }: SuperbrainSceneProps) {
  const activeBoost = mode === 'synthesize' ? 1 : mode === 'orchestrate' ? 0.78 : activity;
  const burstRef = useRef<BurstState>({ lastBurst: 0, intensity: 0 });
  const cameraPushRef = useRef<CameraPushState>({ value: 0 });
  const directivePendingRef = useRef(false);
  const replyGlowRef = useRef(0);
  const metabolismRef = useRef(getTurnMetabolismSnapshot());
  const metabolismColorRef = useRef(new THREE.Color(metabolismRef.current.tint));
  const restLandedAtRef = useRef(-1); // clock (s) the being last LANDED back to rest (one-shot exhale)
  const wasRestRef = useRef(false); // rising-edge detector for the rest landing
  const uniforms = SCENE_UNIFORMS;
  
  const idleRef = useRef<IdleControllerState>({
    lastInputMs: Number.POSITIVE_INFINITY,
    progress: 0,
    blend: 0,
    yaw: 0,
    cascadeIndex: 0,
    nextCascadeAt: -1,
    wasIdle: false,
  });

  const waveRef = useRef({
    slot: 0,
    nextAuto: -1,
    random: createSeededRandom(0x5e4713a9),
    pending: [] as THREE.Vector3[],
  });

  // Approval hold: the supervised mind defers to its operator. Captured
  // breath is frozen, the organism turns amber, and the hold releases on the
  // operator's decision (approval-resolved) or when the conversation moves on.
  const holdRef = useRef({ active: false, breathAtHold: 0.5 });

  // The being's posture, mirrored into a ref so the frame loop reads it without
  // re-rendering. Reduced-motion is now REACTIVE (useReducedMotion): the value is
  // synced into the ref each render so the frame loop stays ref-cheap, AND a live
  // OS toggle re-renders → re-evaluates autoRotate + the prop-fed children below.
  const reducedMotion = useReducedMotion();
  /** OrbitControls handle so OrganismFraming can damp the target height (points). */
  const orbitRef = useRef<{ target: THREE.Vector3 } | null>(null);
  const reducedMotionRef = useRef(reducedMotion);
  reducedMotionRef.current = reducedMotion;
  const arrivalScalarRef = useRef(0); // shared with AccretionCore/CosmicBackground/NeuralAura
  const postureRef = useRef({
    state: LifecycleState.BOOTING as LifecycleState,
    mode: ArrivalMode.COALESCENCE as ArrivalMode,
    enteredAt: 0,
  });
  useEffect(
    () =>
      subscribeLifecycle((snap) => {
        postureRef.current.state = snap.state;
        if (snap.arrivalMode) postureRef.current.mode = snap.arrivalMode;
        postureRef.current.enteredAt = performance.now();
      }),
    [],
  );

  useEffect(
    () =>
      subscribeTurnMetabolism((snapshot) => {
        metabolismRef.current = snapshot;
      }),
    [],
  );

  // Nervous system: a directive from the command bar surges the engine — an
  // immediate cognition burst plus a camera push impulse CameraDrift decays.
  // Burst / knowledge events additionally queue a thought-wave on the cortex,
  // anchored near the matching anatomical region when the event is labeled.
  useEffect(
    () =>
      subscribeCognition((event) => {
        // Cinematic priority: during the opening, the scene ignores ambient
        // cognition so the coalescence isn't broken by stray bursts/waves.
        if (postureRef.current.state === LifecycleState.ARRIVING) return;
        if (event.type === 'approval-required') {
          const hold = holdRef.current;
          hold.active = true;
          hold.breathAtHold = uniforms.uBreath.value; // freeze mid-inhale
          // A slow, attentive dolly-in: the camera leans toward the held mind.
          cameraPushRef.current.value = Math.max(cameraPushRef.current.value, 0.8);
          return;
        }
        if (
          event.type === 'approval-resolved' ||
          event.type === 'directive' ||
          event.type === 'synthesis'
        ) {
          holdRef.current.active = false;
        }
        if (event.type === 'voice-speaking') {
          const phase = String(event.data?.phase ?? '');
          if (event.source === 'reply' && (phase === 'reply-start' || phase === 'reply' || phase === 'reply-complete')) {
            replyGlowRef.current = Math.max(
              replyGlowRef.current,
              THREE.MathUtils.clamp(event.intensity ?? 0.72, 0.28, 1),
            );
            burstRef.current.intensity = Math.max(burstRef.current.intensity, 0.28);
          }
          return;
        }
        if (event.type === 'approval-resolved' && event.label === 'approved') {
          // The operator's decision executes: a thought-wave fires from the
          // frontal (planning) anchor. A rejection gets no wave — standing
          // down is the absence of one.
          const waves = waveRef.current;
          if (waves.pending.length < 3) {
            waves.pending.push(waveOriginForLabel('CAUSAL DECISION', waves.random));
          }
        }
        if (event.type === 'directive') {
          directivePendingRef.current = true;
          cameraPushRef.current.value = 1;
          // The directive lands NOW: the wires surge as the packet enters.
          burstRef.current.intensity = Math.max(burstRef.current.intensity, 0.6);
          return;
        }
        if (event.type === 'agent-dispatch') {
          // THE LIVING TURN: each REAL dispatched tool fires a thought-wave
          // at the lobe that owns that kind of work — the operator watches
          // the actual turn think, region by region.
          const detail = event.detail ?? '';
          if (detail.startsWith('tool engaged: ')) {
            const tool = detail.slice('tool engaged: '.length);
            const waves = waveRef.current;
            if (waves.pending.length < 3) {
              waves.pending.push(waveOriginForLabel(waveLabelForTool(tool), waves.random));
            }
            burstRef.current.intensity = Math.max(burstRef.current.intensity, 0.45);
          }
          return;
        }
        if (
          event.type === 'knowledge-acquired' &&
          /VERIFICATION GREEN|SKILL MASTERED/.test(event.label ?? '')
        ) {
          // SYNAPSE STORM — reserved for PROVEN work: a real verifier pass,
          // or a trail genuinely promoting to verified. Every anatomical
          // anchor fires at once; mastery hits hardest.
          const waves = waveRef.current;
          waves.pending.length = 0;
          for (const anchor of WAVE_REGION_ANCHORS.slice(0, 3)) {
            waves.pending.push(
              new THREE.Vector3(
                anchor.origin.x + (waves.random() - 0.5) * 0.08,
                anchor.origin.y + (waves.random() - 0.5) * 0.08,
                anchor.origin.z + (waves.random() - 0.5) * 0.08,
              ),
            );
          }
          burstRef.current.intensity = 1;
          cameraPushRef.current.value = Math.max(
            cameraPushRef.current.value,
            /SKILL MASTERED/.test(event.label ?? '') ? 1 : 0.55,
          );
          return;
        }
        if (event.type !== 'burst' && event.type !== 'knowledge-acquired') return;
        const waves = waveRef.current;
        if (waves.pending.length >= 3) return;
        waves.pending.push(waveOriginForLabel(event.label, waves.random));
      }),
    [uniforms],
  );

  // Idle attract-mode input sensing: every user input stamps the controller;
  // the frame loop below converts "30 s with no input" into the idle blend.
  // The timestamp is set at MOUNT (not Infinity), so idle starts ONLY after
  // a full 30 s quiet period following mount — never during the e2e window.
  useEffect(() => {
    const idle = idleRef.current;
    // Infinity = "cannot go idle yet"; the frame loop stamps real "now" the
    // moment the being reaches REST, so the idle clock starts only after the
    // opening cinematic settles (never during arrival).
    idle.lastInputMs = Number.POSITIVE_INFINITY;
    idle.progress = 0;
    idle.blend = 0;
    idle.wasIdle = false;
    idle.nextCascadeAt = -1;
    const reset = () => {
      idle.lastInputMs = performance.now();
    };
    const opts: AddEventListenerOptions = { passive: true };
    window.addEventListener('pointermove', reset, opts);
    window.addEventListener('pointerdown', reset, opts);
    window.addEventListener('keydown', reset, opts);
    window.addEventListener('wheel', reset, opts);
    return () => {
      window.removeEventListener('pointermove', reset);
      window.removeEventListener('pointerdown', reset);
      window.removeEventListener('keydown', reset);
      window.removeEventListener('wheel', reset);
      // Park the controller: Infinity means "cannot go idle" until remount.
      idle.lastInputMs = Number.POSITIVE_INFINITY;
      idle.progress = 0;
      idle.blend = 0;
      idle.wasIdle = false;
      idle.nextCascadeAt = -1;
    };
  }, []);

  useFrame((state, delta) => {
    if (FeatureGate.isSleeping) return; // The mirror must know when the animal is sleeping

    const time = state.clock.elapsedTime;
    const current = burstRef.current;
    const hold = holdRef.current;
    const metabolism = metabolismRef.current;
    const metabolismMotionScale = reducedMotionRef.current ? 0.35 : 1;
    const metabolismRate =
      metabolism.phase === 'error'
        ? 7.2
        : metabolism.phase === 'working'
          ? 4.4
          : metabolism.phase === 'thinking'
            ? 2.8
            : metabolism.phase === 'approval'
              ? 1.2
              : 1.8;
    const metabolismPulse = reducedMotionRef.current
      ? 0.5
      : 0.5 + 0.5 * Math.sin(time * metabolismRate + metabolism.changedAt * 0.001);
    // Reply speaking-glow lingers a touch longer so the cortex visibly brightens
    // for the whole reply, not just per-chunk flickers (Phase-6 "it talks back").
    replyGlowRef.current = THREE.MathUtils.damp(replyGlowRef.current, 0, 1.8, delta);

    // The hold blend eases in/out; while engaged the organism neither bursts,
    // free-associates, nor drifts into the idle attract mode.
    uniforms.uHold.value = THREE.MathUtils.damp(
      uniforms.uHold.value,
      hold.active ? 1 : 0,
      2.5,
      delta,
    );
    const holding = uniforms.uHold.value;
    if (hold.active) idleRef.current.lastInputMs = performance.now();

    if (holding < 0.5 &&
        (directivePendingRef.current || time - current.lastBurst > 8 + Math.sin(time * 0.13) * 2)) {
      directivePendingRef.current = false;
      current.lastBurst = time;
      current.intensity = 1;
      // The HUD reacts to the SAME pulse the 3D scene feels.
      
    }
    current.intensity = THREE.MathUtils.damp(current.intensity, 0, 3.5, delta);
    // Decay the directive camera surge here (the ref is owned by this scope);
    // CameraDrift only reads it.
    cameraPushRef.current.value = THREE.MathUtils.damp(cameraPushRef.current.value, 0, 2, delta);

    /* ── shared sentience uniforms: one write per frame drives every layer ── */
    uniforms.uTime.value = time;

    /* ── opening envelopes: coalescence/awaken drive shader-side reveals ── */
    const posture = postureRef.current;
    const sinceState = performance.now() - posture.enteredAt;
    let arrivalTarget = 0;
    let igniteTarget = 0;
    let awakenTarget = 0;
    if (posture.state === LifecycleState.ARRIVING) {
      if (reducedMotionRef.current) {
        // Reduced-motion: skip the streaming coalescence/funnel (a vestibular
        // trigger) and show the settled REST state now — final state preserved.
        arrivalTarget = 0;
        igniteTarget = 0;
      } else {
        const env = coalescenceEnvelope(sinceState);
        // The cortex reveal/dim is shared by both arrival modes (dark -> light).
        // COALESCENCE (first load) ALSO streams the knowledge field inward —
        // uArrival drives the accretion inflow + star funnel; AWAKENING (every
        // return) keeps the field calm so it reads as a distinct "it woke from
        // a seed" beat, not a re-summoning of the whole field.
        arrivalTarget = env.arrival;
        // Both modes ignite from a seed (the single-shot flash in the cortex).
        igniteTarget = ignitionPulse(sinceState);
      }
    } else if (posture.state === LifecycleState.ATTENTIVE) {
      awakenTarget = reducedMotionRef.current ? 1 : awakenNotice(sinceState);
    }
    awakenTarget = Math.max(awakenTarget, replyGlowRef.current);
    uniforms.uArrival.value = arrivalTarget;
    uniforms.uIgnite.value = igniteTarget;
    // AWAKENING return: the cortex still reveals/ignites, but the field stays
    // calm — only COALESCENCE feeds the streaming inflow/funnel scalar.
    arrivalScalarRef.current =
      posture.state === LifecycleState.ARRIVING && posture.mode === ArrivalMode.AWAKENING
        ? 0
        : arrivalTarget;
    // State-driven, interruptible (design law for the reaction): uAwaken eases
    // toward its target so a second directive / pointer move retargets it
    // smoothly and it never blocks input — never a looped pulse.
    uniforms.uAwaken.value = THREE.MathUtils.damp(uniforms.uAwaken.value, awakenTarget, 6, delta);

    // Asymmetric 0.1 Hz systole layered with slower swells at decreasing
    // amplitude — never a constant ~1 Hz pulse.
    const systole = Math.pow(0.5 + 0.5 * Math.sin(time * 0.628), 1.8);
    const swell = 0.5 + 0.5 * Math.sin(time * TAU * 0.043 + 1.7);
    const tide = 0.5 + 0.5 * Math.sin(time * TAU * 0.017 + 4.2);
    const breath = systole * 0.62 + swell * 0.26 + tide * 0.12;
    const metabolicBreath = THREE.MathUtils.clamp(
      breath + metabolism.breathGain * metabolismMotionScale * (0.55 + metabolismPulse * 0.45),
      0,
      1.35,
    );
    // REST EXHALE (#wow signature 5): on LANDING back to rest (from completion /
    // reabsorbing), the being lets out one slow breath — a brief exhale DIP then settle,
    // instead of snapping straight into idle breathing. Reduced motion: no dip.
    const atRest = getOrganismPhase() === 'rest';
    if (atRest && !wasRestRef.current) restLandedAtRef.current = time;
    wasRestRef.current = atRest;
    const sinceRest = restLandedAtRef.current >= 0 ? time - restLandedAtRef.current : 999;
    const restExhale =
      !reducedMotionRef.current && sinceRest < 0.9
        ? -Math.sin(THREE.MathUtils.clamp(sinceRest / 0.9, 0, 1) * Math.PI) * 0.16
        : 0;
    // The approval hold freezes the breath exactly where it was caught.
    uniforms.uBreath.value = Math.max(
      0,
      THREE.MathUtils.lerp(metabolicBreath, hold.breathAtHold, holding) + restExhale,
    );
    uniforms.uRimGain.value = 1.4 * (0.85 + 0.3 * uniforms.uBreath.value);
    uniforms.uSssScale.value = 0.9 * (0.8 + 0.4 * uniforms.uBreath.value);
    uniforms.uBurst.value = Math.max(
      current.intensity,
      metabolism.rootExcitation * metabolismMotionScale * (0.35 + metabolismPulse * 0.65),
    );

    // Virtual rose backlight BEHIND the brain (view space, ~opposite the
    // camera), slowly orbiting ±15° so the transmission cue wanders.
    uniforms.uBackLightDir.value
      .set(Math.sin(time * 0.07) * 0.27, 0.1 + Math.sin(time * 0.043) * 0.2, -1)
      .normalize();

    // Mode tint eases into the core glow (15% mix happens in the shader);
    // the approval hold pulls it toward YELLOW-zone amber on top.
    uniforms.uModeTint.value.lerp(
      MODE_EMISSIVE[mode] ?? MODE_EMISSIVE.observe,
      Math.min(1, delta * 2.5),
    );
    if (metabolism.phase !== 'rest') {
      metabolismColorRef.current.set(metabolism.tint);
      uniforms.uModeTint.value.lerp(
        metabolismColorRef.current,
        Math.min(1, delta * 3.1) * Math.min(0.72, metabolism.intensity * metabolismMotionScale),
      );
    }
    if (holding > 0.01) {
      uniforms.uModeTint.value.lerp(HOLD_TINT, Math.min(1, delta * 2.5) * holding);
    }

    // ── Posture (spectral-v1): the whole body reads its state off its hue.
    //    Damp toward the live lifecycle phase's posture color/flow so state
    //    changes GLIDE. Tint stays low at rest (canon look) and rises once alive.
    // An active CHAT turn (GagosChrome) drives the conversation posture with
    // PRIORITY so the being visibly comes alive — thinking purple → streaming
    // cyan → complete green — then falls back to the idle organism phase.
    const livePhase = getEffectiveOrganismPhase();
    const bodyPosture = deriveBodyPosture({ phase: livePhase });
    const [postureR, postureG, postureB] = postureColor01(bodyPosture.color);
    POSTURE_SCRATCH.setRGB(postureR, postureG, postureB);
    uniforms.uPosture.value.lerp(POSTURE_SCRATCH, Math.min(1, delta * 3.0));
    // Each posture carries its OWN spectral-v1 tint strength (rest≈0 clean →
    // stream/error strong) so every posture's intensity matches the demoplan;
    // POSTURE_DIAL.brainScale is the global multiplier the operator tunes.
    const postureTintTarget = Math.min(0.8, bodyPosture.tint * POSTURE_DIAL.brainScale);
    uniforms.uPostureTint.value = THREE.MathUtils.damp(
      uniforms.uPostureTint.value,
      postureTintTarget * (reducedMotionRef.current ? 0.8 : 1),
      2.5,
      delta,
    );
    uniforms.uFlow.value = THREE.MathUtils.damp(
      uniforms.uFlow.value,
      bodyPosture.flow * POSTURE_DIAL.flowScale,
      2.0,
      delta,
    );
    uniforms.uPostureCommit.value = THREE.MathUtils.damp(
      uniforms.uPostureCommit.value,
      THREE.MathUtils.clamp(POSTURE_DIAL.commit, 0, 1),
      2.5,
      delta,
    );

    /* ── thought-wave scheduler: Poisson-ish idle waves + event waves ── */
    const waves = waveRef.current;
    if (waves.nextAuto < 0) waves.nextAuto = time + 2 + waves.random() * 3;
    if (holding < 0.5 && postureRef.current.state !== LifecycleState.ARRIVING && time >= waves.nextAuto) {
      waves.pending.push(randomWaveOrigin(waves.random));
      waves.nextAuto = time + 3 + waves.random() * 5;
    }

    /* ── idle attract-mode: autonomous cognition after 30 s of no input ── */
    const idle = idleRef.current;
    // Start the idle clock only once the opening has settled to REST — the
    // attract-mode must never engage mid-arrival.
    if (postureRef.current.state === LifecycleState.REST && idle.lastInputMs === Number.POSITIVE_INFINITY) {
      idle.lastInputMs = performance.now();
    }
    const idleForS = (performance.now() - idle.lastInputMs) / 1000;
    const isIdle = idleForS >= IDLE_DELAY_S && !isTextEntryFocused();
    idle.progress = isIdle
      ? Math.min(1, idle.progress + delta / IDLE_EASE_IN_S)
      : Math.max(0, idle.progress - delta / IDLE_EASE_OUT_S);
    // smoothstep — CameraDrift multiplies this into its yaw/pitch math.
    idle.blend = idle.progress * idle.progress * (3 - 2 * idle.progress);
    idle.yaw += IDLE_YAW_RATE * idle.blend * delta;

    if (isIdle) {
      if (!idle.wasIdle || idle.nextCascadeAt < 0) {
        // Idle just began — schedule the first cascade 6–9 s out (seeded).
        idle.nextCascadeAt = time + 6 + waves.random() * 3;
      } else if (time >= idle.nextCascadeAt) {
        idle.nextCascadeAt = time + 6 + waves.random() * 3;
        // Thought cascade: fire a cortex wave NOW from a seeded rotating
        // anatomical anchor (never unseeded randomness — the pending queue
        // drains this same frame), and log the unprompted inference.
        idle.cascadeIndex = (idle.cascadeIndex + 1) % WAVE_REGION_ANCHORS.length;
        const anchor = WAVE_REGION_ANCHORS[idle.cascadeIndex].origin;
        if (waves.pending.length < 3) {
          waves.pending.push(
            new THREE.Vector3(
              anchor.x + (waves.random() - 0.5) * 0.1,
              anchor.y + (waves.random() - 0.5) * 0.1,
              anchor.z + (waves.random() - 0.5) * 0.1,
            ),
          );
        }
        
      }
    }
    idle.wasIdle = isIdle;

    while (waves.pending.length > 0) {
      const origin = waves.pending.shift()!;
      uniforms.uWaveOrigins.value[waves.slot].copy(origin);
      uniforms.uWaveTimes.value[waves.slot] = time;
      waves.slot = (waves.slot + 1) % 3;
    }
  });

  return (
    <>
      {BEING_MODE === 'points' ? (
        /* Poster framing: low FOV (near-orthographic flatness), dollied back,
           front-on; orbit-able. Replaces the drifting cinematic camera in
           points mode so the organism reads like the flat 2D poster. */
        <>
          {/* Clean knowledgeable void — no horizon/atmosphere layer (operator:
              remove the translucent layer from the space). Identity/status live
              in the 2D GagosChrome layer. */}
          <PerspectiveCamera makeDefault fov={26} near={0.1} far={100} position={[0, -0.5, 15]} />
          <OrbitControls
            ref={orbitRef as never}
            makeDefault
            enablePan={false}
            target={[0, -0.5, 0]}
            enableDamping
            dampingFactor={0.08}
            minDistance={6}
            maxDistance={40}
            autoRotate={!reducedMotionRef.current}
            autoRotateSpeed={VOYAGE_SPEED}
          />
          {/* Step-1 framing: fill portrait/mobile (fov + target by aspect). */}
          <OrganismFraming controlsRef={orbitRef} />
        </>
      ) : (
        <CameraDrift activity={activeBoost} burst={burstRef} push={cameraPushRef} idleRef={idleRef} />
      )}

      {/* Cinematic deep space background */}
      {/* The sky serves the VOYAGE: the operator's knowledge field flying
          past the camera IS the forward motion of the thesis. The optional
          photographic dome sits far behind it for depth — it may add to the
          voyage, never replace it. (Dome skipped on low tier: the
          full-screen fbm pass is the budget, and the brain is the show.) */}
      {sky === 'layered' && tier !== 'low' && BEING_MODE !== 'points' && (
        <KnowledgeHorizon activity={activeBoost} />
      )}
      <CosmicBackground tier={tier} arrival={arrivalScalarRef} reducedMotion={reducedMotion} />
      {/* the command nerve as a real 3D tube (operator: "nerve should be 3D, like a
          live") — bridges the DOM -> button to the cauda convergence in the scene. */}
      {BEING_MODE === 'points' && <CommandNerve3D reducedMotion={reducedMotion} />}

      {/* The recall stream: distant glints are REAL trails from the pheromone
          map (strength = core brightness, walks = cage size, freshness =
          spin, quarantine = red stain); each absorb fires a label-anchored
          cortical burst at the matching anatomical region. Dormant when no
          trails are known — nothing pretends to arrive. */}
      {tier !== 'low' && BEING_MODE !== 'points' && <CognitiveGrasp activity={activeBoost} />}

      {/* The brain's life written in stars — real trails only, see the
          component header. Outside Float: the galaxy is the world the mind
          moves through, not a passenger on its bob. */}
      {SHOW_MEMORY_GALAXY && BEING_MODE !== 'points' && <MemoryGalaxy />}

      {/* Post-processing lives ONLY in <PostFX/> (mounted below). A second
          EffectComposer here used to render the entire scene twice per frame
          with its bloom output overwritten by PostFX — pure GPU waste on a
          machine sharing memory bandwidth with a local LLM. */}

      {/* The cortex shader is self-lit and ignores scene lights — this rig
          exists for the OTHER scene objects (accretion core). */}
      <color attach="background" args={['#000000']} />
      <ambientLight intensity={0.14} color="#241145" />
      <directionalLight position={[-6, 7, 1]} intensity={0.41} color="#8fa8ff" />
      <directionalLight position={[7, -2, 0]} intensity={0.42} color="#bcd0ff" />
      <directionalLight position={[0, -3, -8]} intensity={0.39} color="#795cff" />
      <pointLight position={[-4.5, 2.8, -1]} intensity={1.0} distance={10} color="#5e8dff" />
      <pointLight position={[3.5, 4.0, 3]} intensity={0.7} distance={12} color="#c8a8ff" />
      <pointLight position={[4.2, -2.6, -5]} intensity={0.6 + activeBoost * 0.6} distance={8} color="#ff5c9a" />

      <Float speed={0.46 + activeBoost * 0.18} rotationIntensity={0.025} floatIntensity={0.1}>
        <BrainModel activity={activeBoost} mode={mode} burst={burstRef} uniforms={uniforms} tier={tier} surface={surface} arrival={arrivalScalarRef} />
        {/* Accretion disk overlays the MESH being; in points mode the cloud is the being. */}
        {BEING_MODE !== 'points' && (
          <SubsystemErrorBoundary name="AccretionCore">
            <AccretionCore activity={activeBoost} burst={burstRef} arrival={arrivalScalarRef} sceneUniforms={uniforms} />
          </SubsystemErrorBoundary>
        )}
      </Float>

      {tier !== 'low' && BEING_MODE !== 'points' && (
        <PointerBrainClone uniforms={uniforms} tier={tier} reducedMotion={reducedMotionRef.current} />
      )}
      
      {/* Kept OUTSIDE Float so the bottom wires stay rigidly attached to the static UI.
          The top wires plug deep inside the brain, so they just slide 0.1 units inside the brain as it bobs.
          In points mode the spine/roots are part of the BrainPointField cloud, so the
          mesh nerve tree is gated off (it was the hot-green source). */}
      {BEING_MODE !== 'points' && (
        <SubsystemErrorBoundary name="NervousSystem">
          <NervousSystem burst={burstRef} uniforms={uniforms} tier={tier} reducedMotion={reducedMotionRef.current} />
        </SubsystemErrorBoundary>
      )}

      {BEING_MODE === 'points' && <BodySpeech />}

      <PostFX />
    </>
  );
}

preloadBrainScene(); // overlap the GLB parse with boot (see brainScene.ts)
