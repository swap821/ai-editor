import { describe, expect, it } from 'vitest';
import { deriveSurfaceShapeGrammar, SURFACE_SHAPE_DIMENSIONS } from './surfaceShapeGrammar';

describe('surfaceShapeGrammar', () => {
  it('makes the input surface a stem-attached membrane with a curved free lower edge', () => {
    const shape = deriveSurfaceShapeGrammar({
      kind: 'input',
      lifecycle: 'live',
      focused: true,
      role: 'intake',
      originLocal: [0, -1.08, -0.42],
      targetLocal: [0.28, -0.78, 0.16],
      dimensions: SURFACE_SHAPE_DIMENSIONS.input,
    });

    expect(shape.surfaceClass).toBe('intake');
    expect(shape.attachment.kind).toBe('brainstem-inferior');
    expect(shape.attachment.edges).toEqual(['top']);
    expect(shape.attachment.freeEdges).toEqual(['bottom']);
    expect(shape.tension.controlOffsetPx).toBeGreaterThanOrEqual(8);
    expect(shape.tension.controlOffsetPx).toBeLessThanOrEqual(24);
    expect(shape.tension.bottomCurve).toBeGreaterThan(0);
    expect(shape.gripMarks.every((mark) => mark.source === 'stem')).toBe(true);
    expect(shape.rules.satisfiedCount).toBeGreaterThanOrEqual(4);
  });

  it('makes approval a bilateral root-held decision membrane', () => {
    const shape = deriveSurfaceShapeGrammar({
      kind: 'approval',
      lifecycle: 'live',
      focused: true,
      role: 'decision',
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.8, -1.03, 0.32],
      dimensions: SURFACE_SHAPE_DIMENSIONS.approval,
      actuator: { tension: 0.82, stiffness: 0.74, textureMix: 0.58, role: 'holding' },
    });

    expect(shape.surfaceClass).toBe('decision');
    expect(shape.attachment.kind).toBe('bilateral-roots');
    expect(shape.attachment.edges).toEqual(['left', 'right']);
    expect(shape.gripMarks.filter((mark) => mark.edge === 'left')).toHaveLength(2);
    expect(shape.gripMarks.filter((mark) => mark.edge === 'right')).toHaveLength(2);
    expect(shape.thickness.attachmentPx).toBeGreaterThan(shape.thickness.freePx);
    expect(shape.puncta.attachmentDensity).toBeGreaterThan(shape.puncta.freeDensity);
    expect(shape.rules.satisfiedCount).toBe(5);
  });

  it('anchors content to the vertebra-side edge and deforms root grips locally', () => {
    const shape = deriveSurfaceShapeGrammar({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      role: 'work',
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      dimensions: SURFACE_SHAPE_DIMENSIONS.content,
      actuator: { tension: 0.68, stiffness: 0.5, textureMix: 0.48, role: 'conducting' },
    });

    expect(shape.attachment.kind).toBe('vertebra-left');
    expect(shape.attachment.edges).toEqual(['left']);
    expect(shape.attachment.freeEdges).toEqual(['right']);
    expect(shape.gripMarks).toHaveLength(4);
    expect(shape.gripMarks.every((mark) => mark.edge === 'left')).toBe(true);
    expect(shape.gripMarks.every((mark) => mark.indentPx >= 2 && mark.indentPx <= 6)).toBe(true);
    expect(shape.contour.attachmentPinch).toBeGreaterThan(0);
  });

  it('keeps waiting surfaces anatomical but less tense than focused work', () => {
    const base = {
      kind: 'content' as const,
      lifecycle: 'live' as const,
      role: 'waiting' as const,
      originLocal: [0.04, -1.2, -0.34] as const,
      targetLocal: [0.86, -1.03, 0.36] as const,
      dimensions: SURFACE_SHAPE_DIMENSIONS.content,
      actuator: { tension: 0.52, stiffness: 0.48, textureMix: 0.4, role: 'waiting' },
    };
    const focused = deriveSurfaceShapeGrammar({ ...base, focused: true });
    const waiting = deriveSurfaceShapeGrammar({ ...base, focused: false, waitingIndex: 2 });

    expect(waiting.surfaceClass).toBe('waiting');
    expect(waiting.gripMarks[0].intensity).toBeLessThan(focused.gripMarks[0].intensity);
    expect(waiting.puncta.count).toBeLessThan(focused.puncta.count);
    expect(waiting.rules.satisfiedCount).toBeGreaterThanOrEqual(4);
  });

  it('preserves the original content attachment while turning failures into correction scars', () => {
    const shape = deriveSurfaceShapeGrammar({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      role: 'scar',
      originLocal: [0.04, -1.2, -0.34],
      targetLocal: [0.86, -1.03, 0.36],
      dimensions: SURFACE_SHAPE_DIMENSIONS.content,
      actuator: { tension: 0.9, stiffness: 0.82, textureMix: 0.7, role: 'error' },
    });

    expect(shape.surfaceClass).toBe('correction');
    expect(shape.attachment.kind).toBe('vertebra-left');
    expect(shape.puncta.disruption).toBeGreaterThan(0.4);
    expect(shape.contour.scarDisruption).toBeGreaterThan(0);
    expect(shape.gripMarks[0].indentPx).toBeGreaterThan(4);
  });
});
