#!/usr/bin/env bash

echo "Setup Linux build environment"
trap 'echo "::error::Linux setup failed at line $LINENO"; exit 1' ERR

df -h .

##########################################################################
# GET DEPENDENCIES
##########################################################################

apt_packages=(
  coreutils
  curl
  gawk
  git
  lcov
  libasound2-dev
  libcups2-dev
  libfontconfig1-dev
  libfreetype6-dev
  libgcrypt20-dev
  libgl1-mesa-dev
  libglib2.0-dev
  libjack-dev
  libnss3-dev
  libportmidi-dev
  libpulse-dev
  librsvg2-dev
  libsndfile1-dev
  libssl-dev
  libtool
  make
  p7zip-full
  sed
  unzip
  wget
  )

apt_packages_runtime=(
  # Alphabetical order please!
  libdbus-1-3
  libegl1-mesa-dev
  libgles2-mesa-dev
  libodbc2
  libpq-dev
  libssl-dev
  libxcomposite-dev
  libxcursor-dev
  libxi-dev
  libxkbcommon-x11-0
  libxrandr2
  libxtst-dev
  libdrm-dev
  libxcb-cursor-dev
  libxcb-icccm4
  libxcb-image0
  libxcb-keysyms1
  libxcb-randr0
  libxcb-render-util0
  libxcb-xinerama0
  libxcb-xkb-dev
  libxkbcommon-dev
  libopengl-dev
  libvulkan-dev
  )

apt_packages_ffmpeg=(
  ffmpeg
  libavcodec-dev
  libavformat-dev
  libswscale-dev
  )

apt_packages_pw_deps=(
  libdbus-1-dev
  libudev-dev
  )

##########################################################################
# DOWNLOAD WITH A TIME LIMIT, THEN INSTALL
##########################################################################

# A mirror can crawl without stalling: one job spent its whole 30-minute
# timeout on 141 of 266 packages. apt's own retries and timeouts only catch a
# dead connection, so each attempt also gets a time limit. The 107 MB download
# usually takes under 20 s, but 15 of 261 jobs took over 2 minutes, and most of
# those over 5. A limit that is too short costs little, since the next attempt
# continues from what was already downloaded.
apt_attempt_limit=${APT_ATTEMPT_LIMIT:-120} # seconds
apt_max_attempts=3
apt_options=(
  -o Acquire::Retries=3
  -o Acquire::http::Timeout=30
  -o Acquire::https::Timeout=30
)
apt_lists_ready=false

limited_apt_get() {
  # timeout signals its whole process group, which includes apt's download
  # workers, so a killed attempt leaves no lock behind.
  sudo timeout --kill-after=15 "$apt_attempt_limit" \
    apt-get "${apt_options[@]}" "$@"
}

use_next_mirror() {
  # Runner images list mirrors by priority in this file, Azure's first. apt
  # moves down the list when a request fails, not when it is slow, so take
  # Azure off the list.
  local mirrors=/etc/apt/apt-mirrors.txt
  if [[ -f $mirrors ]]; then
    sudo sed -i '/azure\.archive\.ubuntu\.com/d' "$mirrors"
    apt_lists_ready=false
  fi
}

# Download what `apt-get install "$@"` needs, without installing it. A killed
# attempt loses little: finished debs stay in /var/cache/apt/archives, partial
# ones in its partial/ folder, and the next attempt continues from those.
fetch_packages() {
  local attempt start=$SECONDS
  for (( attempt = 1; attempt <= apt_max_attempts; attempt++ )); do
    if (( attempt > 1 )); then
      echo "::warning::apt attempt $(( attempt - 1 )) failed or passed ${apt_attempt_limit}s; trying the next mirror"
      use_next_mirror
    fi
    if { "$apt_lists_ready" || limited_apt_get update; } \
      && limited_apt_get install -y --download-only "$@"; then
      apt_lists_ready=true
      echo "apt download succeeded on attempt $attempt of $apt_max_attempts after $(( SECONDS - start ))s"
      return 0
    fi
  done
  echo "::error::apt download failed after $apt_max_attempts attempts of up to ${apt_attempt_limit}s each"
  return 1
}

# `linux-setup.sh tests` installs only what the tests need: the libraries that
# PySide6's wheels link against and the runner image lacks. To check this list
# after a PySide6 or image update, run `ldd` over the wheels' .so files.
if [[ ${1:-} == tests ]]; then
  apt_install_args=(
    --no-install-recommends
    # Alphabetical order please!
    libegl1
    libpulse0
    libxcb-cursor0
    libxcb-icccm4
    libxcb-image0
    libxcb-keysyms1
    libxcb-render-util0
    libxcb-shape0
    libxcb-util1
    libxcb-xkb1
    libxkbcommon-x11-0
  )
  fetch_packages "${apt_install_args[@]}"
  sudo apt-get install -y --no-download "${apt_install_args[@]}"
  exit 0
fi

apt_install_args=(
  --no-install-recommends
  "${apt_packages[@]}"
  "${apt_packages_runtime[@]}"
  "${apt_packages_ffmpeg[@]}"
  "${apt_packages_pw_deps[@]}"
)
fetch_packages "${apt_install_args[@]}"
sudo apt-get install -y --no-download "${apt_install_args[@]}"

##########################################################################
# PIPEWIRE
##########################################################################

apt_install_args=(pipewire-media-session- wireplumber)
fetch_packages "${apt_install_args[@]}"
sudo apt-get install -y --no-download "${apt_install_args[@]}"

systemctl --user --now enable wireplumber.service
