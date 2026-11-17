export function computeTrustLevel(metrics) {
  if (!metrics) return 'unknown';
  const interventionRate = metrics.human_intervention_rate;
  const verificationCoverage = metrics.verification_coverage;
  if (typeof interventionRate !== 'number' || !Number.isFinite(interventionRate)
    || typeof verificationCoverage !== 'number' || !Number.isFinite(verificationCoverage)) return 'unknown';
  // Green: low intervention, high verification
  if (interventionRate < 0.3 && verificationCoverage > 0.7) return 'healthy';
  // Red: high intervention or very low verification
  if (interventionRate > 0.7 || verificationCoverage < 0.3) return 'critical';
  // Amber: middle ground
  return 'attention';
}
