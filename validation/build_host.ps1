[CmdletBinding()]
param(
    [string] $Compiler
)

# Native Windows counterpart of build_host.sh.  The DSP build itself uses TI
# cl6x; this harness deliberately uses a host C compiler to run the A/B tests.
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here
$Effect = Join-Path $Root 'embedded\effects\duke'
$Out = Join-Path $Here 'host_duke.exe'
$Includes = @("/I$Effect\build", "/I$Effect")
$Sources = @(
    (Join-Path $Here 'host_main.c'),
    (Join-Path $Effect 'duke.c'),
    (Join-Path $Effect 'tables_data.c')
)

if (-not $Compiler) {
    $vcvars = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
    if (Test-Path -LiteralPath $vcvars) {
        $Compiler = 'cl'
    }
    foreach ($candidate in 'gcc', 'cl', 'clang') {
        if ($Compiler) { break }
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            $Compiler = $candidate
            break
        }
    }
    if (-not $Compiler -and (Test-Path -LiteralPath 'C:\Program Files\LLVM\bin\clang.exe')) {
        $Compiler = 'C:\Program Files\LLVM\bin\clang.exe'
    }
}
if ($Compiler -eq 'cl') {
    # cl.exe needs INCLUDE/LIB/PATH from the VS developer environment.
    $vcvars = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
    if (-not (Test-Path -LiteralPath $vcvars)) {
        throw "MSVC environment script not found: $vcvars"
    }
    cmd.exe /c "`"$vcvars`" >nul && set" | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            Set-Item -Path ("Env:" + $matches[1]) -Value $matches[2]
        }
    }
}
if (-not $Compiler) {
    throw 'No host C compiler found. Install MSVC Build Tools (Desktop development with C++) or LLVM/MinGW, then rerun this script.'
}

if ($Compiler -eq 'cl') {
    & cl /nologo /O2 /std:c11 /W4 /wd4100 @Includes @Sources "/Fe:$Out"
} else {
    & $Compiler -O2 -std=c99 -Wall -Wextra -Wno-unused-parameter "-I$Effect\build" "-I$Effect" @Sources -lm "-o$Out"
}
if ($LASTEXITCODE -ne 0) { throw "Host compiler '$Compiler' failed with exit code $LASTEXITCODE." }
Write-Host "built $Out with $Compiler"
