$url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$extractedDir = "ffmpeg-6.0-essentials_build"
$executablePath = ".\$localFolder\bin\ffmpeg.exe"

mkdir ffmpeg

$ProgressPreference = 'SilentlyContinue'

Write-Host "Downloading ffmpeg..."
Invoke-WebRequest -Uri $url -OutFile .\ffmpeg\dwn.zip
Write-Host "Download completed."

Write-Host "Extracting zip..."
Expand-Archive -Path .\ffmpeg\dwn.zip -DestinationPath .\ffmpeg
Write-Host "Extracted."

$ProgressPreference = 'Continue'

# copy to target dir
Copy-Item -Path ".\ffmpeg\$extractedDir\bin\ffmpeg.exe" -Destination .\ffmpeg

# cleanup
Remove-Item -Path .\ffmpeg\dwn.zip
Remove-Item -Path ".\ffmpeg\$extractedDir" -Recurse
