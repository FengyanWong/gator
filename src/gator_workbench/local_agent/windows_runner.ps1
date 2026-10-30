param([Parameter(Mandatory=$true)][string]$Spec)
# Fixed supervisor, not a model-provided script. Cancellation kills only the Process
# object this invocation started; an expired lease also cleans up after a backend crash.
$ErrorActionPreference = 'Stop'
$s = Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json
$child = $null
try {
    $child = Start-Process -FilePath $s.executable -ArgumentList $s.arguments -WorkingDirectory $s.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput $s.stdout -RedirectStandardError $s.stderr
    $nativeHandle = $child.Handle
    while (-not $child.HasExited) {
        if ((Test-Path -LiteralPath $s.cancel) -or (([DateTime]::UtcNow - (Get-Item -LiteralPath $s.lease).LastWriteTimeUtc).TotalSeconds -gt 30)) {
            $child.Kill()
            $child.WaitForExit()
            exit 130
        }
        Start-Sleep -Milliseconds 100
        $child.Refresh()
    }
    $child.WaitForExit()
    # Retaining the native handle above keeps ExitCode available after Refresh.
    if ($null -eq $child.ExitCode) { exit 1 }
    exit $child.ExitCode
} finally {
    if ($null -ne $child) {
        if (-not $child.HasExited) { $child.Kill(); $child.WaitForExit() }
        $child.Dispose()
    }
}
