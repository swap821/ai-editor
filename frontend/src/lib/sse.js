// Parse a Server-Sent Events buffer into discrete frames.
//
// Returns the `frames` fully decoded so far plus any trailing `rest` that is not
// yet a complete frame (no terminating blank line), so the caller can carry it
// into the next network chunk. Mirrors the agent stream's wire format: each
// frame is an optional `event:` line plus a `data:` line, frames separated by a
// blank line. A frame with no `data:` line is skipped.
export function parseSseBuffer(buffer) {
  const parts = buffer.split('\n\n');
  const rest = parts.pop() ?? '';
  const frames = [];
  for (const part of parts) {
    let event = 'message';
    let data = '';
    for (const line of part.split('\n')) {
      if (line.startsWith('event: ')) event = line.slice(7).trim();
      else if (line.startsWith('data: ')) data = line.slice(6);
    }
    if (data) frames.push({ event, data });
  }
  return { frames, rest };
}
