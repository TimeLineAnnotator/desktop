url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
extractedDir="ffmpeg-6.0-essentials_build"
executablePath="./$extractedDir/bin/ffmpeg"

mkdir -p ffmpeg

echo "Downloading ffmpeg..."
wget -q $url -O ./ffmpeg/dwn.zip
echo "Download completed."

echo "Extracting zip..."
unzip -q ./ffmpeg/dwn.zip -d ./ffmpeg
echo "Extracted."

# copy to convenient location
cp "./ffmpeg/$extractedDir/bin/ffmpeg" ./ffmpeg

# cleanup
rm ./ffmpeg/dwn.zip
rm -r "./ffmpeg/$extractedDir"
