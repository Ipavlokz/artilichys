$ErrorActionPreference = 'Stop'
try {
    Write-Host 'Antes de continuar, detiene Artilichys con Ctrl+C y cierra su ventana.'
    Read-Host 'Presiona Enter cuando este detenido' | Out-Null
    $candidates = @(
        (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'artilichys'),
        (Join-Path $env:USERPROFILE 'OneDrive\Documentos\artilichys'),
        (Join-Path $env:USERPROFILE 'Documents\artilichys')
    ) | Select-Object -Unique
    $found = @($candidates | Where-Object {Test-Path (Join-Path $_ 'neurovisual\cli.py')})
    if ($found.Count -eq 1) {
        $target = $found[0]
    } else {
        $shell = New-Object -ComObject Shell.Application
        $folder = $shell.BrowseForFolder(0, 'Selecciona la carpeta artilichys que usas para ejecutar el programa', 0, 0)
        if (!$folder) { throw 'Instalacion cancelada.' }
        $target = $folder.Self.Path
    }
    if (!(Test-Path (Join-Path $target 'neurovisual\cli.py'))) {
        throw 'La carpeta seleccionada no contiene Artilichys.'
    }
    $files = @('CONECTAR_UNICORN.cmd','README.md','neurovisual\cli.py','neurovisual\config.py',
        'neurovisual\output.py','neurovisual\pipeline.py','tests\test_visual_config.py','tests\test_gestures.py')
    $backup = Join-Path $target ('respaldo-gestos-' + [Guid]::NewGuid().ToString('N'))
    foreach ($relative in $files) {
        $source = Join-Path $PSScriptRoot $relative
        if (!(Test-Path $source)) { throw "Falta $relative. Extrae todo el ZIP antes de ejecutar." }
    }
    $copied = 0
    foreach ($relative in $files) {
        $destination = Join-Path $target $relative
        $sourcePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $relative))
        $destinationPath = [IO.Path]::GetFullPath($destination)
        if ([String]::Equals($sourcePath, $destinationPath, [StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        if (Test-Path $destination) {
            $saved = Join-Path $backup $relative
            New-Item -ItemType Directory -Force (Split-Path $saved) | Out-Null
            Copy-Item -LiteralPath $destination -Destination $saved
        }
        New-Item -ItemType Directory -Force (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath $sourcePath -Destination $destination -Force
        $copied++
    }
    Write-Host "Actualizacion instalada en: $target"
    if ($copied -eq 0) {
        Write-Host 'Los archivos ya estaban extraidos en la carpeta de Artilichys; no hace falta copiarlos otra vez.'
    } else {
        Write-Host "Archivos anteriores respaldados en: $backup"
    }
    Write-Host 'No se han modificado grabaciones ni licencias. Esto instala la actualizacion; falta validar los detectores con datos reales.'
} catch {
    Write-Host "No se pudo completar: $_" -ForegroundColor Red
    exit 1
}
