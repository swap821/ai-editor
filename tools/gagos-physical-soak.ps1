param(
  [Parameter(Mandatory = $true)]
  [string]$BrowserPath,
  [string]$Url = 'http://localhost:5186/',
  [int]$Samples = 150,
  [int]$IntervalsPerSample = 4,
  [int]$IntervalMilliseconds = 3000
)

$ErrorActionPreference = 'Stop'
# browse.exe writes informational startup/status lines to stderr. Keep strict
# PowerShell errors for the collector itself without promoting that native
# process chatter into a terminating error; validity is checked from the JSON
# probe below instead.
if ($null -ne (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)) {
  $PSNativeCommandUseErrorActionPreference = $false
}
$records = @()
$invalidBatch = $null

$probeTemplate = @'
(()=>{
  const samples = window.__getFrontendMetrics?.() ?? [];
  const values = (name) => samples.filter((sample) => sample.name === name).map((sample) => sample.value);
  const p50 = values('frame-time-p50');
  const p95 = values('frame-time-p95');
  const dropped = values('dropped-frame-period');
  const sceneSamples = window.__getFrontendSceneDiagnostics?.() ?? [];
  const scene = sceneSamples.at(-1) ?? null;
  return JSON.stringify({
    soakBatch: __BATCH__,
    sampleCount: samples.length,
    perf: window.__getPerf?.() ?? null,
    frameP50: p50.at(-1) ?? null,
    frameP95: p95.at(-1) ?? null,
    droppedCount: dropped.length,
    droppedMax: dropped.length ? Math.max(...dropped) : null,
    sceneSampleCount: sceneSamples.length,
    scene,
    domNodes: document.getElementsByTagName("*").length,
    canvas: document.querySelectorAll("canvas").length,
    heap: performance.memory
      ? { used: performance.memory.usedJSHeapSize, total: performance.memory.totalJSHeapSize }
      : null
  });
})()
'@

$steps = @()
for ($batch = 1; $batch -le $Samples; $batch += 1) {
  if ($batch -eq 1) {
    $steps += , @('goto', $Url)
  }
  $steps += , @('wait', '.scene-layer canvas')

  for ($interval = 1; $interval -le $IntervalsPerSample; $interval += 1) {
    $id = (($batch - 1) * $IntervalsPerSample) + $interval
    $steps += , @(
      'js',
      "setTimeout(() => document.body.setAttribute('data-gagos-soak-$id', 'ready'), $IntervalMilliseconds); 'scheduled'"
    )
    $steps += , @('wait', "[data-gagos-soak-$id=ready]")
    if ($interval -eq $IntervalsPerSample) {
      $probe = $probeTemplate.Replace('__BATCH__', $batch.ToString())
      $steps += , @('js', $probe)
    } else {
      $steps += , @('js', "'heartbeat'")
    }
  }

}

# Preserve the command tuples as nested arrays. A single browser chain keeps
# the page/renderer alive across every batch; invoking browse.exe once per
# batch allowed its daemon to reset between otherwise-valid observations.
$payload = ConvertTo-Json -InputObject @($steps) -Compress
$previousErrorActionPreference = $ErrorActionPreference
try {
  # browse.exe writes informational startup/status lines to stderr, which
  # Windows PowerShell can promote to NativeCommandError under strict mode.
  # Relax only this process boundary; structured probe output is validated
  # below and still fail-closes when it is absent or malformed.
  $ErrorActionPreference = 'Continue'
  Write-Output ("SOAK_CHAIN_STARTED batches=$Samples intervals=$IntervalsPerSample intervalMs=$IntervalMilliseconds")
  $raw = @($payload | & $BrowserPath chain 2>&1 | ForEach-Object { "$_" })
} finally {
  $ErrorActionPreference = $previousErrorActionPreference
}

$probeLines = @($raw | Where-Object { $_ -match '^\[js\]\s*\{.*\}$' })
foreach ($line in $probeLines) {
  try {
    $record = (($line -replace '^\[js\]\s*', '').Trim() | ConvertFrom-Json)
  } catch {
    continue
  }
  $batch = [int]$record.soakBatch
  if ($null -ne $invalidBatch) { continue }
  $valid = [int]$record.canvas -eq 1 -and [int]$record.domNodes -ge 50 -and $null -ne $record.perf -and $null -ne $record.scene
  if ($valid) { $valid = [int]$record.scene.sceneObjects -ge 1 }
  if (-not $valid) {
    $invalidBatch = $batch
    Write-Output ("SOAK_INVALID_PAGE batch=$batch canvas=$($record.canvas) dom=$($record.domNodes) samples=$($record.sampleCount) sceneSamples=$($record.sceneSampleCount) sceneObjects=$($record.scene.sceneObjects)")
    continue
  }
  $records += $record
  if ($batch -eq 1 -or $batch % 10 -eq 0) {
    Write-Output ("SOAK_PROGRESS batch=$batch sampleCount=$($record.sampleCount) dom=$($record.domNodes) canvas=$($record.canvas) scene=$($record.scene.sceneObjects) pool=$($record.scene.transientPoolSize) p50=$($record.frameP50) p95=$($record.frameP95) factor=$($record.perf.factor) dpr=$($record.perf.dpr)")
  }
}

if ($null -eq $invalidBatch -and $records.Count -lt $Samples) {
  $invalidBatch = $records.Count + 1
  Write-Output ("SOAK_INVALID_BATCH=$invalidBatch")
  $raw | Select-Object -Last 10
}

if ($records.Count -eq 0) {
  Write-Output ("SOAK_END completed=0 invalidBatch=$invalidBatch")
  exit 1
}

$dom = @($records | ForEach-Object { [double]$_.domNodes })
$canvas = @($records | ForEach-Object { [double]$_.canvas })
$factors = @($records | Where-Object { $_.perf } | ForEach-Object { [double]$_.perf.factor })
$dprs = @($records | Where-Object { $_.perf } | ForEach-Object { [double]$_.perf.dpr })
$drops = @($records | Where-Object { $null -ne $_.droppedMax } | ForEach-Object { [double]$_.droppedMax })
$sceneObjects = @($records | Where-Object { $_.scene } | ForEach-Object { [double]$_.scene.sceneObjects })
$transientPools = @($records | Where-Object { $_.scene } | ForEach-Object { [double]$_.scene.transientPoolSize })
$geometries = @($records | Where-Object { $_.scene } | ForEach-Object { [double]$_.scene.geometries })
$textures = @($records | Where-Object { $_.scene } | ForEach-Object { [double]$_.scene.textures })
$renderCalls = @($records | Where-Object { $_.scene } | ForEach-Object { [double]$_.scene.renderCalls })
$summary = [ordered]@{
  requestedSamples = $Samples
  completedSamples = $records.Count
  invalidBatch = $invalidBatch
  domMin = ($dom | Measure-Object -Minimum).Minimum
  domMax = ($dom | Measure-Object -Maximum).Maximum
  canvasMin = ($canvas | Measure-Object -Minimum).Minimum
  canvasMax = ($canvas | Measure-Object -Maximum).Maximum
  factorMin = if ($factors.Count) { ($factors | Measure-Object -Minimum).Minimum } else { $null }
  factorMax = if ($factors.Count) { ($factors | Measure-Object -Maximum).Maximum } else { $null }
  dprMin = if ($dprs.Count) { ($dprs | Measure-Object -Minimum).Minimum } else { $null }
  dprMax = if ($dprs.Count) { ($dprs | Measure-Object -Maximum).Maximum } else { $null }
  droppedMax = if ($drops.Count) { ($drops | Measure-Object -Maximum).Maximum } else { $null }
  sceneObjectsMin = if ($sceneObjects.Count) { ($sceneObjects | Measure-Object -Minimum).Minimum } else { $null }
  sceneObjectsMax = if ($sceneObjects.Count) { ($sceneObjects | Measure-Object -Maximum).Maximum } else { $null }
  transientPoolMin = if ($transientPools.Count) { ($transientPools | Measure-Object -Minimum).Minimum } else { $null }
  transientPoolMax = if ($transientPools.Count) { ($transientPools | Measure-Object -Maximum).Maximum } else { $null }
  geometriesMin = if ($geometries.Count) { ($geometries | Measure-Object -Minimum).Minimum } else { $null }
  geometriesMax = if ($geometries.Count) { ($geometries | Measure-Object -Maximum).Maximum } else { $null }
  texturesMin = if ($textures.Count) { ($textures | Measure-Object -Minimum).Minimum } else { $null }
  texturesMax = if ($textures.Count) { ($textures | Measure-Object -Maximum).Maximum } else { $null }
  renderCallsMin = if ($renderCalls.Count) { ($renderCalls | Measure-Object -Minimum).Minimum } else { $null }
  renderCallsMax = if ($renderCalls.Count) { ($renderCalls | Measure-Object -Maximum).Maximum } else { $null }
  lastFrameP50 = $records[-1].frameP50
  lastFrameP95 = $records[-1].frameP95
}
Write-Output ("SOAK_END " + ($summary | ConvertTo-Json -Compress))
