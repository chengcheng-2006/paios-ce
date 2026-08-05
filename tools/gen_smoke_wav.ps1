# Phase 9A real smoke: generate a disposable spoken WAV via Windows SAPI.
# Output: <out>  (a short spoken English WAV)
param(
    [Parameter(Mandatory = $true)][string]$Out
)

$ErrorActionPreference = "Stop"
try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SetOutputToWaveFile($Out)
    $synth.Speak("Hello from PAIOS CE local speech test. One two three four five.")
    $synth.Dispose()
    Write-Output "WAV_GENERATED: $Out"
    $f = Get-Item $Out
    Write-Output "SIZE_BYTES: $($f.Length)"
    exit 0
} catch {
    Write-Output "SAPI_FAILED: $($_.Exception.Message)"
    exit 1
}
