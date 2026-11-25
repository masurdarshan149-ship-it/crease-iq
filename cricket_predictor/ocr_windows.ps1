# Reads the text in a picture with Windows' own text recognition (offline, free). Used by pitch_report.read_image.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr_windows.ps1 <image path>   -> one line of text per line
param([Parameter(Mandatory = $true)][string]$Path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($operation, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $null = $task.Wait(-1)
    $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path -LiteralPath $Path).Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US')) }
if ($null -eq $engine) { throw 'Windows text recognition is not installed for English on this PC.' }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$stream.Dispose()
# A wide gap between two words on one line (side-by-side columns, like two teams on a TV graphic) is written as " | "
foreach ($line in $result.Lines) {
    $words = @($line.Words)
    if ($words.Count -eq 0) { continue }
    $text = $words[0].Text
    for ($i = 1; $i -lt $words.Count; $i++) {
        $a = $words[$i - 1].BoundingRect; $b = $words[$i].BoundingRect
        $gap = $b.X - ($a.X + $a.Width)
        $tall = [Math]::Max($a.Height, $b.Height)
        if ($gap -gt 1.6 * $tall) { $text += ' | ' } else { $text += ' ' }
        $text += $words[$i].Text
    }
    $text
}
