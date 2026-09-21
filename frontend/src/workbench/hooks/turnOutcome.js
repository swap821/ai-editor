export function isEstablishedTurn(result) {
  return Boolean(result && (result.ok === true || result.paused === true));
}

export function isCompleteWorkResult(result, hasCode) {
  return Boolean(hasCode && result?.ok === true && result?.paused !== true);
}
